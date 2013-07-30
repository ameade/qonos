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

import copy
import datetime

import mock

from qonos.common import timeutils
from qonos.tests.unit.worker import fakes
import qonos.tests.utils as test_utils
from qonos.worker.reaper import reaper


class TestReaper(test_utils.BaseTestCase):
    def setUp(self):
        super(TestReaper, self).setUp()
        self.reaper = reaper.ReaperProcessor()
        self.worker = mock.Mock()
        self.worker.worker_id = fakes.WORKER_ID
        self.job = copy.deepcopy(fakes.JOB['job'])
        self.config(job_retention=100, group='reaper_worker')
        self.reaper.job_retention = 1

    def tearDown(self):
        super(TestReaper, self).tearDown()

    def test_init_processor(self):
        self.assertEqual(self.reaper.job_retention, 1)

        self.reaper.init_processor(self.worker)

        self.assertEqual(self.reaper.job_retention, 100)

    def test_process_job_queued(self):
        self.assertFalse(self.reaper.current_job)
        self.job['status'] = 'QUEUED'
        self.reaper.worker = self.worker
        self.notifier = mock.Mock()
        self.reaper.update_job = mock.Mock()
        self.reaper.delete_jobs = mock.Mock()

        with mock.patch('qonos.common.utils.generate_notification',
                        self.notifier):
            self.reaper.process_job(self.job)

        self.reaper.update_job.assert_any_call(self.job['id'],
                                                       'PROCESSING')
        self.notifier.assert_called_once_with(None, 'qonos.job.run.start',
                                              {'job': self.job}, 'INFO')
        self.assertEqual(self.reaper.current_job, self.job['id'])

        self.reaper.delete_jobs.assert_called_once_with()

        self.reaper.update_job.assert_any_call(self.job['id'],
                                                       'DONE')

    def test_process_job_retry(self):
        self.assertFalse(self.reaper.current_job)
        self.job['status'] = 'ERROR'
        self.reaper.worker = self.worker
        self.notifier = mock.Mock()
        self.reaper.update_job = mock.Mock()
        self.reaper.delete_jobs = mock.Mock()

        with mock.patch('qonos.common.utils.generate_notification',
                        self.notifier):
            self.reaper.process_job(self.job)

        self.reaper.update_job.assert_any_call(self.job['id'],
                                                       'PROCESSING')
        self.notifier.assert_called_once_with(None, 'qonos.job.retry',
                                              {'job': self.job}, 'INFO')
        self.assertEqual(self.reaper.current_job, self.job['id'])

        self.reaper.delete_jobs.assert_called_once_with()

        self.reaper.update_job.assert_any_call(self.job['id'],
                                                       'DONE')

    def test_get_jobs_for_deletion(self):
        cutoff_date = datetime.datetime(2005, 1, 19, 12)
        expected_jobs = [self.job]
        qonos_client = mock.Mock()
        qonos_client.list_jobs.return_value = expected_jobs
        self.reaper.qonos_client = qonos_client
        expected_filters = {'updated_at_max': cutoff_date}

        actual_jobs = self.reaper.get_jobs_for_deletion(cutoff_date)

        qonos_client.list_jobs.assert_called_once_with(expected_filters)
        self.assertEqual(actual_jobs, expected_jobs)

    def test_delete_jobs(self):
        self.reaper.worker = self.worker
        timeutils.set_time_override(datetime.datetime(2005, 1, 20, 12))
        expected_updated_at = datetime.datetime(2005, 1, 19, 12)
        qonos_client = mock.Mock()
        self.reaper.qonos_client = qonos_client
        jobs_to_return = [[self.job, self.job], []]

        self.reaper.get_jobs_for_deletion = mock.Mock()
        self.reaper.get_jobs_for_deletion.side_effect = (lambda x:
                                                        jobs_to_return.pop(0))
        actual_jobs = self.reaper.delete_jobs()

        self.reaper.get_jobs_for_deletion.assert_called_with(
                                                        expected_updated_at)
        actual_length = self.reaper.get_jobs_for_deletion.call_count
        self.assertEqual(2, actual_length)

        qonos_client.delete_job.assert_called_with(self.job['id'])
        actual_deletes = qonos_client.delete_job.call_count
        self.assertEqual(2, actual_deletes)

    def test_delete_job_not_found(self):
        self.reaper.worker = self.worker
        timeutils.set_time_override(datetime.datetime(2005, 1, 20, 12))
        expected_updated_at = datetime.datetime(2005, 1, 19, 12)
        qonos_client = mock.Mock()
        qonos_client.delete_job = mock.Mock(side_effect=Exception("BOOM"))
        self.reaper.qonos_client = qonos_client
        jobs_to_return = [[self.job, self.job], []]

        self.reaper.get_jobs_for_deletion = mock.Mock()
        self.reaper.get_jobs_for_deletion.side_effect = (lambda x:
                                                        jobs_to_return.pop(0))
        actual_jobs = self.reaper.delete_jobs()

        self.reaper.get_jobs_for_deletion.assert_called_with(
                                                        expected_updated_at)
        actual_length = self.reaper.get_jobs_for_deletion.call_count
        self.assertEqual(2, actual_length)

        qonos_client.delete_job.assert_called_with(self.job['id'])
        actual_deletes = qonos_client.delete_job.call_count
        self.assertEqual(2, actual_deletes)
