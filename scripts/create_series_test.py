"""One-off script to create a test series using the first workspace in the DB."""
import sys
import os

# Ensure app is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import SessionLocal
from app.db.models.workspace import Workspace
from app.services.series_service import create_series


def main():
    db = SessionLocal()
    try:
        workspace = db.query(Workspace).first()
        if not workspace:
            print("No workspace found. Register a user first (POST /api/v1/auth/register).")
            return 1
        series = create_series(
            db,
            workspace_id=workspace.id,
            name="Test Motivation Series",
            content_type="motivation",
            custom_topic=None,
        )
        print("Created series:")
        print(f"  id: {series.id}")
        print(f"  name: {series.name}")
        print(f"  contentType: {series.content_type}")
        print(f"  status: {series.status}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
