# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


def test_method():
	"""Regional-override target for erpnext.tests.test_regional.test_method (see
	hooks.py: regional_overrides["France"]). Exists solely to prove erpnext.allow_regional
	dispatches to a country-specific override; not real French localization logic."""
	return "france override"
