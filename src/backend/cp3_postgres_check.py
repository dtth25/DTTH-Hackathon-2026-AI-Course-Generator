import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from alembic import command
from alembic.config import Config
from app.core.config import settings
from app.services import database
from app.models import User, Course
from app.models.provider_call import BookBudget
from app.services.provider_usage import ensure_book_budget, reserve_call, settle_call

url = os.environ['CP3_TEST_DATABASE_URL']
assert '127.0.0.1:55433/cp3' in url
settings.DATABASE_URL = url
config = Config('alembic.ini')
command.upgrade(config, 'head')
engine = create_engine(url)
assert 'provider_calls' in inspect(engine).get_table_names()
command.downgrade(config, 'c9d0e1f2a3b4')
command.upgrade(config, 'head')
factory = sessionmaker(bind=engine)
database.SessionLocal = factory
with factory.begin() as db:
    db.add(User(id='cp3-user', email='cp3@example.com', hashed_password='fake'))
    db.flush()
    course = Course(id='cp3-course', user_id='cp3-user', name='test')
    db.add(course)
    db.flush()
    budget = ensure_book_budget(db, course, 'v1')
with ThreadPoolExecutor(max_workers=8) as pool:
    accepted = list(pool.map(lambda i: reserve_call(budget, str(i), Decimal('.02')), range(8)))
assert sum(accepted) == 4
for i, accepted_call in enumerate(accepted):
    if accepted_call:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: settle_call(str(i), Decimal('.01')), range(4)))
with factory() as db:
    row = db.get(BookBudget, budget)
    assert (row.spent, row.reserved) == (40_000_000, 0)
print('PostgreSQL16: upgrade/downgrade/re-upgrade, independent concurrent reservations and duplicate settlement PASS')
engine.dispose()
