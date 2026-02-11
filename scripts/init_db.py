from app.db.base import Base
from app.db.session import engine
from app.models import entities  # noqa

Base.metadata.create_all(bind=engine)
print("db initialized")
