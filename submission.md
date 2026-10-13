# Mixtape Bug Hunt

## AI usage

I used Codex to read and summarize the repository structure, trace route-to-service calls, run reproductions and tests, and review each change. I checked its explanations against the source and the observed behavior before documenting each root cause. Specific debugging examples appear in the entries below.

## Codebase map

- `app.py` creates the Flask application, configures SQLAlchemy, registers the four route blueprints, and creates database tables.
- `models.py` defines users, songs, tags, listening events, ratings, playlists, and notifications. Its association tables represent friendships, song tags, and ordered playlist entries. Model `to_dict()` methods shape API data.
- `routes/songs.py` handles search, song detail, ratings, and listens. `routes/playlists.py` handles playlist creation, detail, song listing, and additions. `routes/users.py` exposes profiles, streaks, and notifications. `routes/feed.py` exposes listening and activity feeds. Routes parse requests, call services, and return JSON.
- `services/search_service.py` queries songs; `streak_service.py` records listening events and maintains streaks; `feed_service.py` assembles friends' listening activity; `playlist_service.py` creates and retrieves playlists; `notification_service.py` saves ratings and playlist additions and manages notifications.
- `seed_data.py` builds sample users, friendships, songs, tags, listening events, playlists, ratings, and notifications. `tests/` contains focused service tests using in-memory SQLite databases.

**Data flow — rating a song:** `POST /songs/<song_id>/rate` reaches `routes/songs.py`, which reads `user_id` and `score` and calls `notification_service.rate_song()`. The service validates the score and referenced song and user, updates an existing `Rating` or inserts one, commits the transaction, and returns the rating. The route serializes it with `Rating.to_dict()` and responds with JSON. `models.py` enforces one rating per user and song through a unique constraint.

**Organization pattern:** Routes handle HTTP input and output, while services own database queries and feature behavior. Services use the shared SQLAlchemy session from `app.py`; model relationships and association tables connect the entities.

## Root cause analyses

**Issue #1 — My listening streak keeps resetting**

- **How I reproduced it:** Before editing code, I ran `tests/test_streaks.py`. The Saturday June 15 to Sunday June 16 case failed: `update_listening_streak()` left the streak at 1 instead of incrementing it to 2. The surrounding Monday-to-Tuesday, same-day, and skipped-day cases passed.
- **How I found the root cause:** I followed `POST /songs/<song_id>/listen` in `routes/songs.py` to `record_listening_event()` and `update_listening_streak()` in `services/streak_service.py`. The test established that the dates were consecutive; the weekday condition in the increment branch specifically rejected Sunday.
- **The root cause:** `update_listening_streak()` incremented only when `days_since_last == 1 and today.weekday() != 6`. Python's `weekday()` returns 6 for Sunday, so a Saturday-to-Sunday interval of exactly one day fell through to the reset branch.
- **My fix:** Increment whenever `days_since_last == 1`. Calendar-day distance already expresses the rule, including weekend transitions.
- **Side-effect check:** I reran the streak tests to check Sunday, ordinary consecutive days, repeated listens on one day, first listens, and a skipped day.

**Issue #2 — Friends Listening Now shows people from yesterday**

- **How I reproduced it:** Before editing code, I fixed the feed clock at Sunday 09:00 UTC, set a friend's last listening event to Saturday 23:00 UTC, and requested `GET /feed/<nova_id>/listening-now`. The friend appeared despite having no Sunday listen.
- **How I found the root cause:** I traced `routes/feed.py` into `get_friends_listening_now()` in `services/feed_service.py`, then compared the event timestamp filter with the endpoint's calendar-day expectation. The query included the previous night's event because it was less than 24 hours old.
- **The root cause:** The service used `now - timedelta(hours=24)` as its cutoff. At 09:00, this allows events from 09:00 on the previous calendar day onward, so yesterday evening remains in the feed.
- **My fix:** Set the cutoff to midnight of the current UTC calendar day. The existing query and latest-event-per-friend selection then operate only on today's events.
- **Side-effect check:** I added `tests/test_feed.py`, a regression test at the day boundary: yesterday at 23:59 is excluded and today at 00:00 is included. The activity feed remains separately unfiltered by date.

**Issue #3 — The same song keeps showing up twice in search**

- **How I reproduced it:** Before editing code, `GET /songs/search?q=Anthem` returned three identical entries for Crown Heights Anthem. The existing multi-tag search test also failed with three results; one-tag and no-tag search cases passed.
- **How I found the root cause:** I followed `routes/songs.py` to `search_songs()` in `services/search_service.py`, then compared the outer join to the `song_tags` association in `models.py`. The three copies matched the song's three tag rows, confirming that the query result cardinality came from the join.
- **The root cause:** The outer join produces one SQL row per matching song/tag pair. SQLAlchemy's `.scalars().all()` retained each repeated `Song` entity, and the service serialized all of them. The join was unnecessary for matching titles or artists, but its repeated rows reached the response.
- **My fix:** Add `.unique()` to the scalar result before `.all()`, so each matching `Song` entity is serialized once while retaining the existing outer-join query.
- **Side-effect check:** I reran all search tests, covering title and artist matches, songs with zero, one, and three tags, and a query with no matches.

**Issue #4 — I got notified when a friend added my song to a playlist but not when they rated it**

- **How I reproduced it:** Before editing code, I posted a five-star rating from kenji to a song shared by aaliya. `POST /songs/<song_id>/rate` returned 201, but aaliya's `song_rated` notification count stayed at zero.
- **How I found the root cause:** I traced the rate route in `routes/songs.py` to `rate_song()` in `services/notification_service.py`, then compared it with `add_to_playlist()` in the same service. The playlist path calls `create_notification()` after saving the action; the rating path returned immediately after committing the rating.
- **The root cause:** `rate_song()` saved the `Rating` but never created a `Notification`. Since notification retrieval reads stored rows, neither the immediate response nor later `GET /users/<id>/notifications` could show a rating notification.
- **My fix:** After committing a rating, call `create_notification()` for the song's sharer with the rater, song, and score, unless the sharer rated their own song. This follows the existing playlist-add notification pattern.
- **Side-effect check:** I added `tests/test_notifications.py` to verify the rating persists, a friend rating appears through the notifications endpoint, and rating one's own song does not create a self-notification.

**Issue #5 — The last song in a playlist never shows up**

- **How I reproduced it:** Before editing code, `GET /playlists/<Friday Energy id>/songs` returned six songs for a playlist seeded with seven entries. Existing tests likewise returned four of five tracks and omitted the last title.
- **How I found the root cause:** I followed `routes/playlists.py` to `get_playlist_songs()` in `services/playlist_service.py`. The database query sorted all playlist entries by position, but the return expression sliced off the final song. This explained why adding another song would reveal the previous last song while hiding the new one.
- **The root cause:** `songs[:-1]` excludes the final element of the ordered query result on every request. An empty playlist still returned an empty list, masking the issue there.
- **My fix:** Serialize all queried songs without slicing. The query already restricts them to the requested playlist and orders them by position.
- **Side-effect check:** I reran the playlist tests for complete count, position order, and an empty playlist, then ran the full suite.
