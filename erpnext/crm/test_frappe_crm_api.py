# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

from unittest import mock

import frappe

from erpnext.crm.frappe_crm_api import create_prospect_against_crm_deal
from erpnext.tests.utils import ERPNextTestSuite


class TestFrappeCRMAPI(ERPNextTestSuite):
	"""Regression coverage for the transaction-safety fix in create_prospect_against_crm_deal.

	A failed Prospect insert used to recover with a bare `frappe.db.rollback()`. On PostgreSQL a
	failed insert aborts the whole DB transaction, so a full rollback (rather than a scoped
	savepoint) silently discards any work already committed earlier in the same request — exactly
	the bug already fixed once in this same file for create_customer's contact/address linking
	(see the "crm_customer_links" savepoint there). This test locks the same fix in for the
	Prospect path: recovery must use `frappe.db.savepoint("crm_create_prospect")` /
	`frappe.db.rollback(save_point="crm_create_prospect")`, not a bare rollback.
	"""

	def setUp(self):
		self.form_dict_backup = frappe.form_dict
		frappe.form_dict = frappe._dict(
			{
				"organization": f"Test Prospect Sync {frappe.generate_hash(length=8)}",
				"lead_name": None,
				"no_of_employees": None,
				"deal_owner": None,
				"erpnext_company": None,
				"crm_deal": "test-deal-001",
				"territory": None,
				"industry": None,
				"website": None,
				"annual_revenue": None,
				"contacts": None,
				"address": None,
			}
		)

	def tearDown(self):
		frappe.form_dict = self.form_dict_backup
		super().tearDown()

	@ERPNextTestSuite.change_settings(
		"CRM Settings",
		{
			"enable_frappe_crm_data_synchronization": 1,
			"allowed_users": [{"user": "Administrator"}],
		},
	)
	def test_failed_prospect_insert_uses_scoped_savepoint(self):
		with (
			mock.patch("frappe.new_doc") as mock_new_doc,
			mock.patch("frappe.db.savepoint") as mock_savepoint,
			mock.patch("frappe.db.rollback") as mock_rollback,
		):
			mock_prospect = mock.Mock()
			mock_prospect.insert.side_effect = frappe.DuplicateEntryError
			mock_new_doc.return_value = mock_prospect

			# Must not raise: the handler is expected to recover from the failed insert.
			create_prospect_against_crm_deal()

			mock_savepoint.assert_any_call("crm_create_prospect")
			mock_rollback.assert_called_once_with(save_point="crm_create_prospect")
