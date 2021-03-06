from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB

from aleph.core import db
from aleph.util import expand_json
from aleph.model.collection import Collection


class CrawlerState(db.Model):
    """Report the state of a file being processed."""

    TIMEOUT = timedelta(minutes=60)

    STATUS_OK = 'ok'
    STATUS_FAIL = 'fail'

    id = db.Column(db.BigInteger, primary_key=True)
    crawler_id = db.Column(db.Unicode(), index=True)
    crawler_run = db.Column(db.Unicode(), nullable=True)
    content_hash = db.Column(db.Unicode(65), nullable=True, index=True)
    foreign_id = db.Column(db.Unicode, nullable=True, index=True)
    status = db.Column(db.Unicode(10), nullable=False)
    error_type = db.Column(db.Unicode(), nullable=True)
    error_message = db.Column(db.Unicode(), nullable=True)
    error_details = db.Column(db.Unicode(), nullable=True)
    meta = db.Column(JSONB)
    collection_id = db.Column(db.Integer(), db.ForeignKey('collection.id'), index=True)  # noqa
    collection = db.relationship(Collection, backref=db.backref('crawl_states', cascade='all, delete-orphan'))  # noqa
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @classmethod
    def _from_meta(cls, meta, collection_id):
        obj = cls()
        obj.collection_id = collection_id
        obj.crawler_id = meta.crawler
        obj.crawler_run = meta.crawler_run
        obj.foreign_id = meta.foreign_id
        obj.content_hash = meta.content_hash
        obj.meta = expand_json(meta.to_attr_dict(compute=True))
        db.session.add(obj)
        return obj

    @classmethod
    def store_stub(cls, collection_id, crawler_id, crawler_run):
        obj = cls()
        obj.collection_id = collection_id
        obj.crawler_id = crawler_id
        obj.crawler_run = crawler_run
        obj.error_type = 'init'
        obj.status = cls.STATUS_OK
        db.session.add(obj)
        return obj

    @classmethod
    def store_ok(cls, meta, collection_id):
        obj = cls._from_meta(meta, collection_id)
        obj.status = cls.STATUS_OK
        return obj

    @classmethod
    def store_fail(cls, meta, collection_id, error_type=None,
                   error_message=None, error_details=None):
        obj = cls._from_meta(meta, collection_id)
        obj.status = cls.STATUS_FAIL
        obj.error_type = error_type
        obj.error_message = error_message
        obj.error_details = error_details
        return obj

    @classmethod
    def crawler_last_run(cls, crawler_id):
        q = db.session.query(cls.crawler_run, cls.created_at)
        q = q.filter(cls.crawler_id == crawler_id)
        q = q.order_by(cls.created_at.desc())
        q = q.limit(1)
        res = q.first()
        if res is None:
            return None, None
        return (res.crawler_run, res.created_at)

    @classmethod
    def crawler_stats(cls, crawler_id):
        stats = {}
        last_run_id, last_run_time = cls.crawler_last_run(crawler_id)

        # Check if the crawler was active very recently, if so, don't
        # allow the user to execute a new run right now.
        timeout = (datetime.utcnow() - CrawlerState.TIMEOUT)
        stats['running'] = last_run_time > timeout if last_run_time else False

        q = db.session.query(func.count(cls.id))
        q = q.filter(cls.crawler_id == crawler_id)
        for section in ['last', 'all']:
            data = {}
            sq = q
            if section == 'last':
                sq = sq.filter(cls.crawler_run == last_run_id)
            okq = sq.filter(cls.status == cls.STATUS_OK)
            data['ok'] = okq.scalar() - 1 if last_run_id else 0
            failq = sq.filter(cls.status == cls.STATUS_FAIL)
            data['fail'] = failq.scalar() if last_run_id else 0
            stats[section] = data
        stats['last']['updated'] = last_run_time
        stats['last']['run_id'] = last_run_id
        return stats

    @classmethod
    def all(cls):
        return db.session.query(CrawlerState)

    def to_dict(self):
        return {
            'id': self.id,
            'status': self.status,
            'crawler_id': self.crawler_id,
            'crawler_run': self.crawler_run,
            'content_hash': self.content_hash,
            'foreign_id': self.foreign_id,
            'error_type': self.error_type,
            'error_message': self.error_message,
            'error_details': self.error_details,
            'meta': self.meta,
            'collection_id': self.collection_id,
            'created_at': self.created_at
        }

    def __repr__(self):
        return '<CrawlerState(%r,%r)>' % (self.id, self.status)

    def __unicode__(self):
        return self.id
