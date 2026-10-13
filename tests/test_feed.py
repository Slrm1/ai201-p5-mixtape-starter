"""Calendar-day behavior of the Friends Listening Now endpoint."""

from datetime import datetime, timezone
from unittest.mock import patch

from app import create_app, db
from models import ListeningEvent, Song, User, friendships
from services import feed_service


def test_listening_now_includes_today_and_excludes_yesterday():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        viewer = User(username="viewer", email="viewer@example.com")
        yesterday_friend = User(username="yesterday", email="yesterday@example.com")
        today_friend = User(username="today", email="today@example.com")
        db.session.add_all([viewer, yesterday_friend, today_friend])
        db.session.flush()
        song = Song(title="Test Song", artist="Test Artist", shared_by=viewer.id)
        db.session.add(song)
        db.session.flush()
        for friend in (yesterday_friend, today_friend):
            db.session.execute(friendships.insert().values(user_id=viewer.id, friend_id=friend.id))
        db.session.add_all([
            ListeningEvent(user_id=yesterday_friend.id, song_id=song.id,
                           listened_at=datetime(2024, 6, 15, 23, 59, tzinfo=timezone.utc)),
            ListeningEvent(user_id=today_friend.id, song_id=song.id,
                           listened_at=datetime(2024, 6, 16, 0, 0, tzinfo=timezone.utc)),
        ])
        db.session.commit()

        class FixedDateTime:
            @staticmethod
            def now(tz=None):
                return datetime(2024, 6, 16, 9, 0, tzinfo=timezone.utc)

        with patch.object(feed_service, "datetime", FixedDateTime):
            response = app.test_client().get(f"/feed/{viewer.id}/listening-now")

        assert response.status_code == 200
        assert [item["friend"]["username"] for item in response.json["feed"]] == ["today"]
