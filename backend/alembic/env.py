from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from alembic import context
from app.core.config import get_settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Real connection string comes from app.core.config (DATABASE_URL in backend/.env),
# not from alembic.ini — one source of truth, no secret duplicated in a committed file.
settings = get_settings()
if not settings.database_url:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to backend/.env — see backend/.env.example."
    )
config.set_main_option("sqlalchemy.url", settings.database_url)

# Each domain module's models must be imported here so its SQLModel classes register
# on this metadata and `autogenerate` can see them.
from app.modules.ask.models import Conversation, ConversationTurn  # noqa: E402, F401
from app.modules.assignments.models import (  # noqa: E402, F401
    Assignment,
    AssignmentSubmission,
)
from app.modules.billing.models import (  # noqa: E402, F401
    GenerationUsage,
    OrgPlan,
    UserPlan,
)
from app.modules.documents.models import Document, DocumentChunk  # noqa: E402, F401
from app.modules.flashcards.models import Flashcard, FlashcardReviewState  # noqa: E402, F401
from app.modules.quiz.models import (  # noqa: E402, F401
    Quiz,
    QuizAttempt,
    QuizQuestion,
)
from app.modules.referral.models import ReferralAttribution, ReferralCode  # noqa: E402, F401
from app.modules.subjects.models import Subject  # noqa: E402, F401
from app.modules.telegram.models import (  # noqa: E402, F401
    TelegramLink,
    TelegramLinkCode,
)

target_metadata = SQLModel.metadata

# Objects that live only in Postgres and are managed by hand-written migrations, not by
# any SQLModel model — so autogenerate would otherwise see them in the live DB, not find
# them in `target_metadata`, and propose dropping them on the next revision.
# `document_chunks.text_search_vector` (a GENERATED tsvector column) + its GIN index are
# the FTS half of hybrid retrieval (migration 066f42dbed80); they're deliberately absent
# from the `DocumentChunk` model so the SQLite test engine can still create the table.
_AUTOGENERATE_IGNORE = {
    ("column", "text_search_vector"),
    ("index", "ix_document_chunks_text_search_vector"),
}


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001, ARG001
    return (type_, name) not in _AUTOGENERATE_IGNORE


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
