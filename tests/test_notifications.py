"""Rating notification behavior through the HTTP API."""

from app import create_app, db
from models import Notification, Song, User


def test_rating_notifies_sharer_but_not_self_rating():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        sharer = User(username="sharer", email="sharer@example.com")
        friend = User(username="friend", email="friend@example.com")
        db.session.add_all([sharer, friend])
        db.session.flush()
        song = Song(title="Shared Song", artist="Artist", shared_by=sharer.id)
        db.session.add(song)
        db.session.commit()

        client = app.test_client()
        response = client.post(f"/songs/{song.id}/rate", json={"user_id": friend.id, "score": 5})
        assert response.status_code == 201
        assert response.json["score"] == 5
        notifications = client.get(f"/users/{sharer.id}/notifications").json["notifications"]
        assert len(notifications) == 1
        assert notifications[0]["type"] == "song_rated"
        assert "friend rated your song 'Shared Song' 5 stars" in notifications[0]["body"]

        own_response = client.post(f"/songs/{song.id}/rate", json={"user_id": sharer.id, "score": 4})
        assert own_response.status_code == 201
        assert Notification.query.filter_by(user_id=sharer.id).count() == 1
