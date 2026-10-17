"""Peewee migrations -- 040_add_timeline_camera_timestamp_index.py.

Adds a composite (camera, timestamp) index to the timeline table. The
hourly-timeline API filters by camera and timestamp and orders by timestamp,
but the table only had single-column camera/source indexes, so the query
walked a camera's entire retention history.

"""

import peewee as pw

SQL = pw.SQL


def migrate(migrator, database, fake=False, **kwargs):
    migrator.sql(
        'CREATE INDEX IF NOT EXISTS "timeline_camera_timestamp" '
        'ON "timeline" ("camera", "timestamp")'
    )


def rollback(migrator, database, fake=False, **kwargs):
    migrator.sql('DROP INDEX IF EXISTS "timeline_camera_timestamp"')
