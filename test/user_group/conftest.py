import pytest

from storage import SessionLocal, init_db, engine, Base


@pytest.fixture
def session():
    init_db(engine)
    with SessionLocal() as session:
        yield session

    # need to drop all tables after each test
    # and re-create them
    # otherwise data from previous test will be
    # present in the next test
    Base.metadata.drop_all(bind=engine)
