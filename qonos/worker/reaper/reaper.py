# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright 2013 Rackspace
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import datetime

from oslo.config import cfg

from qonos.common import timeutils
from qonos.openstack.common.gettextutils import _
from qonos.openstack.common import log as logging
from qonos.worker import worker

LOG = logging.getLogger(__name__)

reaper_worker_options = [
    cfg.IntOpt('job_retention', default=180,
               help=_('The max number of days to keep completed jobs in db')),
]

CONF = cfg.CONF
CONF.register_opts(reaper_worker_options, group='reaper_worker')


class ReaperProcessor(worker.JobProcessor):
    """
    Reaper worker cleans up old jobs from the database periodically.

    Uses config 'job_retention' value to determine a cutoff date, where
    all jobs with 'updated_at' earlier than that time are purged from the db.
    """
    def __init__(self):
        super(ReaperProcessor, self).__init__()
        self.current_job = None
        self.job_retention = None
        self.qonos_client = None

    def init_processor(self, worker):
        """
        Job retention refers to the max number of days that a job
        should stay in the database (based on its updated_at) value
        """
        super(ReaperProcessor, self).init_processor(worker)
        self.job_retention = CONF.reaper_worker.job_retention
        self.qonos_client = self.get_qonos_client()

    def process_job(self, job):
        self.current_job = job['id']
        self.update_job(self.current_job, 'PROCESSING')

        LOG.info(_("Clean up job picked up by worker %s")
                % self.worker.worker_id)

        msg = _("Worker %(worker)s processing job: %(job)s")
        LOG.debug(msg % {"worker": self.worker.worker_id,
                         "job": self.current_job})

        payload = {'job': job}
        if job['status'] == 'QUEUED':
            self.send_notification_start(payload)
        else:
            self.send_notification_retry(payload)

        self.delete_jobs()
        self.update_job(self.current_job, 'DONE')

    def get_jobs_for_deletion(self, cutoff_date):
        filters = {'updated_at_max': cutoff_date}
        return self.qonos_client.list_jobs(filters)

    def delete_jobs(self):
        cutoff_date = (timeutils.utcnow() -
                       datetime.timedelta(days=self.job_retention))

        msg = _("Worker %(worker)s deleting jobs not updated since %(date)s")
        LOG.info(msg % {"worker": self.worker.worker_id,
                        "date": timeutils.isotime(cutoff_date)})

        deleted_count = 0
        jobs_to_delete = self.get_jobs_for_deletion(cutoff_date)

        # NOTE(ameade): we choose not to do pagination here. We instead
        # just loop until we get no jobs back to delete. This is because
        # a job that would be used as a pagination marker will be deleted.
        while jobs_to_delete:
            for job in jobs_to_delete:
                msg = _("Deleting job %(job)s")
                LOG.debug(msg % {"job": job['id']})
                try:
                    self.qonos_client.delete_job(job['id'])
                    deleted_count += 1
                except Exception as e:
                    msg = _("Could not delete job %(job)s. Exception: %(e)s")
                    LOG.warn(msg % {"job": job['id'], "e": unicode(e)})
            jobs_to_delete = self.get_jobs_for_deletion(cutoff_date)

        msg = _("Worker %(worker)s successfully deleted %(count)s jobs")
        LOG.info(msg % {"worker": self.worker.worker_id,
                        "count": deleted_count})
