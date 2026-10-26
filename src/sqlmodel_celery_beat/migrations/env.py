from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import sqlmodel_celery_beat.models  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# Set by migrate.run_alembic() when --schema is passed
run_schema = config.get_main_option("run_schema", "") or None


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as conn:
        context.configure(
            connection=conn,
            target_metadata=target_metadata,
            version_table_schema=run_schema,      # alembic_version lives here
            include_schemas=bool(run_schema),
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()