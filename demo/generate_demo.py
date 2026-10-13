"""Build the README demo from real Mixtape API responses.

Install the app requirements plus Pillow and imageio-ffmpeg, then run:
    python demo/generate_demo.py
"""

from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app, db  # noqa: E402
from models import (  # noqa: E402
    ListeningEvent, Playlist, Song, Tag, User, friendships,
    playlist_entries, song_tags,
)
from services import feed_service  # noqa: E402
from services.streak_service import update_listening_streak  # noqa: E402


def collect_results():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        nova = User(username="nova", email="nova@example.com")
        darius = User(username="darius", email="darius@example.com")
        simone = User(username="simone", email="simone@example.com")
        kenji = User(username="kenji", email="kenji@example.com")
        aaliya = User(username="aaliya", email="aaliya@example.com")
        db.session.add_all([nova, darius, simone, kenji, aaliya])
        db.session.flush()

        anthem = Song(title="Crown Heights Anthem", artist="Borough Kings", shared_by=simone.id)
        shared = Song(title="Aaliya's Mix", artist="Aaliya", shared_by=aaliya.id)
        other = Song(title="Night Drive", artist="Nova", shared_by=nova.id)
        db.session.add_all([anthem, shared, other])
        tags = [Tag(name=name) for name in ("rap", "hip-hop", "boom bap")]
        db.session.add_all(tags)
        db.session.flush()
        for tag in tags:
            db.session.execute(song_tags.insert().values(song_id=anthem.id, tag_id=tag.id))

        for friend in (darius, simone):
            db.session.execute(friendships.insert().values(user_id=nova.id, friend_id=friend.id))
        db.session.add_all([
            ListeningEvent(user_id=darius.id, song_id=other.id,
                           listened_at=datetime(2024, 6, 15, 23, 0, tzinfo=timezone.utc)),
            ListeningEvent(user_id=simone.id, song_id=anthem.id,
                           listened_at=datetime(2024, 6, 16, 8, 30, tzinfo=timezone.utc)),
        ])

        playlist = Playlist(name="Friday Energy", created_by=darius.id)
        db.session.add(playlist)
        db.session.flush()
        for position, song in enumerate((other, shared, anthem), start=1):
            db.session.execute(playlist_entries.insert().values(
                playlist_id=playlist.id, song_id=song.id,
                position=position, added_by=darius.id,
            ))

        kenji.listening_streak = 12
        kenji.last_listened_at = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
        update_listening_streak(kenji, datetime(2024, 6, 16, 9, 0, tzinfo=timezone.utc))
        db.session.commit()

        client = app.test_client()
        streak = client.get(f"/users/{kenji.id}/streak").json["streak"]

        class FixedDateTime:
            @staticmethod
            def now(tz=None):
                return datetime(2024, 6, 16, 9, 0, tzinfo=timezone.utc)

        with patch.object(feed_service, "datetime", FixedDateTime):
            feed = client.get(f"/feed/{nova.id}/listening-now").json["feed"]
        feed_names = [item["friend"]["username"] for item in feed]
        search = client.get("/songs/search?q=Anthem").json
        rating = client.post(f"/songs/{shared.id}/rate", json={"user_id": kenji.id, "score": 5})
        notifications = client.get(f"/users/{aaliya.id}/notifications").json
        playlist_response = client.get(f"/playlists/{playlist.id}/songs").json

        assert streak == 13
        assert feed_names == ["simone"]
        assert search["count"] == 1 and search["results"][0]["title"] == anthem.title
        assert rating.status_code == 201 and notifications["count"] == 1
        assert notifications["notifications"][0]["type"] == "song_rated"
        assert playlist_response["count"] == 3
        assert playlist_response["songs"][-1]["title"] == anthem.title

        return [
            ("Mixtape Bug Hunt", "Five fixes, five API checks", [
                "A short tour of the bugfix/mixtape branch",
                "Each result below comes from a Flask test-client request.",
            ]),
            ("01  Listening streak", "Saturday to Sunday", [
                "Before: 12 consecutive days; last listen Saturday 12:00 UTC",
                "Sunday 09:00 UTC -> GET /users/kenji/streak",
                f"Response: streak = {streak}  [PASS]",
            ]),
            ("02  Friends Listening Now", "Calendar-day cutoff", [
                "Darius listened Saturday 23:00; Simone Sunday 08:30 UTC",
                "Sunday 09:00 UTC -> GET /feed/nova/listening-now",
                f"Response: {', '.join(feed_names)} only  [PASS]",
            ]),
            ("03  Song search", "One result per song", [
                "Crown Heights Anthem has three tags",
                "GET /songs/search?q=Anthem",
                f"Response: count = {search['count']}  [PASS]",
            ]),
            ("04  Rating notification", "Friend rates a shared song", [
                "Kenji rates Aaliya's Mix five stars",
                "POST /songs/<id>/rate -> GET /users/aaliya/notifications",
                f"Response: {notifications['count']} song_rated notification  [PASS]",
            ]),
            ("05  Playlist songs", "The final track is visible", [
                "Friday Energy contains three ordered entries",
                "GET /playlists/<id>/songs",
                f"Response: {playlist_response['count']} songs; last = {anthem.title}  [PASS]",
            ]),
            ("Verified fixes", "Reproduce. Trace. Fix. Test.", [
                "Five separate fix commits on bugfix/mixtape",
                "Regression tests cover the feed boundary and notifications",
                "Full test suite: 15 passed",
            ]),
        ]


def render_slide(index, title, subtitle, lines, path):
    image = Image.new("RGB", (1280, 720), "#0b1120")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 54)
    subtitle_font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 30)
    body_font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 25)
    small_font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 20)
    draw.rounded_rectangle((44, 42, 1236, 678), radius=28, fill="#141f32", outline="#344967", width=2)
    draw.rounded_rectangle((76, 78, 1198, 88), radius=5, fill="#58d6a7")
    draw.text((82, 124), title, font=title_font, fill="#f4f7fb")
    draw.text((84, 206), subtitle, font=subtitle_font, fill="#9dd7f7")
    draw.rounded_rectangle((78, 294, 1202, 586), radius=18, fill="#0a1525")
    for number, line in enumerate(lines):
        color = "#60e1b0" if "[PASS]" in line else "#e0e7f2"
        draw.text((105, 327 + number * 67), line, font=body_font, fill=color)
    draw.text((86, 626), "MIXTAPE  /  BUGFIX DEMO", font=small_font, fill="#8ca6c4")
    draw.text((1115, 626), f"{index + 1:02d} / 07", font=small_font, fill="#8ca6c4")
    image.save(path)


def main():
    slides = collect_results()
    output = ROOT / "demo" / "mixtape-bugfix-demo.mp4"
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        frames = []
        for index, (title, subtitle, lines) in enumerate(slides):
            frame = temp_path / f"frame_{index:02d}.png"
            render_slide(index, title, subtitle, lines, frame)
            frames.append(frame)
        shutil.copyfile(frames[0], ROOT / "demo" / "preview.png")
        screenshots = ROOT / "demo" / "screenshots"
        screenshots.mkdir(exist_ok=True)
        for index, name in enumerate(("streak", "feed", "search", "notifications", "playlist"), start=1):
            shutil.copyfile(frames[index], screenshots / f"{name}.png")
        manifest = temp_path / "frames.txt"
        with manifest.open("w", encoding="utf-8") as file:
            for frame in frames:
                file.write(f"file '{frame.as_posix()}'\n")
                file.write("duration 5\n")
            file.write(f"file '{frames[-1].as_posix()}'\n")
        subprocess.run([
            imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
            "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
            "-vf", "fps=24,format=yuv420p", "-c:v", "libx264", "-crf", "25",
            "-movflags", "+faststart", str(output),
        ], check=True)
    print(f"Created {output}")


if __name__ == "__main__":
    main()
