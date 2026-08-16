import frappe

import erpnext
from erpnext.tests.utils import ERPNextTestSuite


@erpnext.allow_regional
def test_method():
	return "original"


class TestInit(ERPNextTestSuite):
	def test_regional_overrides(self):
		self.addCleanup(frappe.flags.pop, "country", None)

		frappe.flags.country = "Maldives"
		self.assertEqual(test_method(), "original")

	def test_regional_override_dispatches_to_registered_country(self):
		"""A country with a registered override (hooks.py: regional_overrides) must actually
		dispatch to it, not just fall back to the original - regression test for the France
		entry pointing at a module that didn't exist (erpnext.regional.france.utils)."""
		self.addCleanup(frappe.flags.pop, "country", None)

		frappe.flags.country = "France"
		self.assertEqual(test_method(), "france override")
