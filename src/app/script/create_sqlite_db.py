from sqlalchemy import create_engine
import app.model as model

def create_sqlite_db():
	sqlite_engine = create_engine("sqlite:///poll.db")
	model.Base.metadata.create_all(sqlite_engine)

if __name__ == "__main__":
	create_sqlite_db()
