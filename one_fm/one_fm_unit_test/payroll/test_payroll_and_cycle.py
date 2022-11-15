# Copyright (c) 2022, ONEFM and Contributors
# See license.txt

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

import erpnext
from erpnext.accounts.utils import get_fiscal_year, getdate, nowdate
from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.payroll.doctype.payroll_entry.payroll_entry import (
	PayrollEntry,
	get_end_date,
	get_start_end_dates,
)
from hrms.payroll.doctype.salary_slip.test_salary_slip import (
	create_account,
	set_salary_component_account,
)
from hrms.payroll.doctype.salary_structure.test_salary_structure import (
	create_salary_structure_assignment,
	make_salary_structure,
)

from erpnext.projects.doctype.project.test_project import make_project

test_dependencies = ["Holiday List"]

class TestPayrollAndCycle(FrappeTestCase):
	def setUp(self):
		for dt in [
			"Salary Slip",
			"Salary Component",
			"Salary Component Account",
			"Payroll Entry",
			"Salary Structure",
			"Salary Structure Assignment",
			"Payroll Employee Detail",
			"Additional Salary"
		]:
			frappe.db.delete(dt)

		make_salary_component(company_list=["_Test Company"])

		project_date = frappe.getdate(today().add_months(-4))

		project_data = [
			{
				'project_name': '_Project 1',
				'start_date': project_date
			},
			{
				'project_name': '_Project 2',
				'start_date': project_date
			},
			{
				'project_name': '_Project 3',
				'start_date': project_date
			}
		]

		for project in project_data:
			make_project(project)

		frappe.db.set_value("Company", "_Test Company", "default_holiday_list", "_Test Holiday List")
		frappe.db.set_value("Payroll Settings", None, "email_salary_slip_to_employee", 0)

		set_hr_and_payroll_additional_settings()

		# set default payable account
		default_account = frappe.db.get_value(
			"Company", "_Test Company", "default_payroll_payable_account"
		)
		if not default_account or default_account != "_Test Payroll Payable - _TC":
			create_account(
				account_name="_Test Payroll Payable",
				company="_Test Company",
				parent_account="Current Liabilities - _TC",
				account_type="Payable",
			)
			frappe.db.set_value(
				"Company", "_Test Company", "default_payroll_payable_account", "_Test Payroll Payable - _TC"
			)

		set_employee_with_project()

		mark_attendance()

	def mark_attendance():
		pass
		# data = {'employee': }
		# for date in data.unmarked_days:
		# 	doc_dict = {
		# 		"doctype": "Attendance",
		# 		"employee": data.employee,
		# 		"attendance_date": get_datetime(date),
		# 		"status": data.status,
		# 		"company": company,
		# 	}
		# 	attendance = frappe.get_doc(doc_dict).insert()
		# 	attendance.submit()

	def set_employee_with_project():
		project_data = [
			{
				'project_name': '_Project 1',
				'user': 'test_employee_1@payroll.com'
			},
			{
				'project_name': '_Project 2',
				'user': 'test_employee_2@payroll.com'
			},
			{
				'project_name': '_Project 3',
				'user': 'test_employee_3@payroll.com'
			}
		]

		for project in project_data:
			make_employee(project.user, company='_Test Company', {'project': project.project_name})

	def set_hr_and_payroll_additional_settings():
		project_data = [
			{
				'project_name': '_Project 1',
				'payroll_start_day': 'Month Start',
				'payroll_end_day': 'Month End'
			},
			{
				'project_name': '_Project 1',
				'payroll_start_day': '11',
				'payroll_end_day': '10'
			}
		]
		hr_and_payroll_additional_settings = frappe.get_doc('HR and Payroll Additional Settings', None)
		hr_and_payroll_additional_settings.default_payroll_start_day = '24'
		hr_and_payroll_additional_settings.default_payroll_end_day = '23'
		for project in project_data:
			project_payroll_cycle = hr_and_payroll_additional_settings.append('project_payroll_cycle')
			project_payroll_cycle.project = project.project_name
			project_payroll_cycle.payroll_start_day = project.payroll_start_day
			project_payroll_cycle.payroll_end_day = project.payroll_end_day

	def test_payroll_entry(self):
		company = frappe.get_doc("Company", "_Test Company")
		employee = frappe.db.get_value("Employee", {"company": "_Test Company"})
		setup_salary_structure(employee, company)

		dates = get_start_end_dates("Monthly", nowdate())
		make_payroll_entry(
			start_date=dates.start_date,
			end_date=dates.end_date,
			payable_account=company.default_payroll_payable_account,
			currency=company.default_currency,
			company=company.name,
		)

def get_payroll_entry(**args):
	args = frappe._dict(args)

	payroll_entry: PayrollEntry = frappe.new_doc("Payroll Entry")
	payroll_entry.company = args.company or erpnext.get_default_company()
	payroll_entry.start_date = args.start_date or "2016-11-01"
	payroll_entry.end_date = args.end_date or "2016-11-30"
	payroll_entry.payment_account = get_payment_account()
	payroll_entry.posting_date = nowdate()
	payroll_entry.payroll_frequency = "Monthly"
	payroll_entry.branch = args.branch or None
	payroll_entry.department = args.department or None
	payroll_entry.payroll_payable_account = args.payable_account
	payroll_entry.currency = args.currency
	payroll_entry.exchange_rate = args.exchange_rate or 1

	if args.cost_center:
		payroll_entry.cost_center = args.cost_center

	if args.payment_account:
		payroll_entry.payment_account = args.payment_account

	payroll_entry.fill_employee_details()
	payroll_entry.insert()

	# Commit so that the first salary slip creation failure does not rollback the Payroll Entry insert.
	frappe.db.commit()  # nosemgrep

	return payroll_entry


def make_payroll_entry(**args):
	payroll_entry = get_payroll_entry(**args)
	payroll_entry.submit()
	payroll_entry.submit_salary_slips()
	if payroll_entry.get_sal_slip_list(ss_status=1):
		payroll_entry.make_payment_entry()

	return payroll_entry


def get_payment_account():
	return frappe.get_value(
		"Account",
		{"account_type": "Cash", "company": erpnext.get_default_company(), "is_group": 0},
		"name",
	)


def make_holiday(holiday_list_name):
	if not frappe.db.exists("Holiday List", holiday_list_name):
		current_fiscal_year = get_fiscal_year(nowdate(), as_dict=True)
		dt = getdate(nowdate())

		new_year = dt + relativedelta(month=1, day=1, year=dt.year)
		republic_day = dt + relativedelta(month=1, day=26, year=dt.year)
		test_holiday = dt + relativedelta(month=2, day=2, year=dt.year)

		frappe.get_doc(
			{
				"doctype": "Holiday List",
				"from_date": current_fiscal_year.year_start_date,
				"to_date": current_fiscal_year.year_end_date,
				"holiday_list_name": holiday_list_name,
				"holidays": [
					{"holiday_date": new_year, "description": "New Year"},
					{"holiday_date": republic_day, "description": "Republic Day"},
					{"holiday_date": test_holiday, "description": "Test Holiday"},
				],
			}
		).insert()

	return holiday_list_name


def setup_salary_structure(employee, company_doc, currency=None, salary_structure=None):
	for data in frappe.get_all("Salary Component", pluck="name"):
		if not frappe.db.get_value(
			"Salary Component Account", {"parent": data, "company": company_doc.name}, "name"
		):
			set_salary_component_account(data)

	make_salary_structure(
		salary_structure or "_Test Salary Structure",
		"Monthly",
		employee,
		company=company_doc.name,
		currency=(currency or company_doc.default_currency),
	)

def make_salary_component(company_list=None):
	salary_components = [
		{
			"salary_component": "Basic Salary",
			"abbr": "BS",
			"condition": "base > 10000",
			"formula": "base",
			"type": "Earning",
			"amount_based_on_formula": 1,
			"depends_on_payment_days": 1,
		},
		{
			"salary_component": "Not Included in Last Salary",
			"abbr": "NIILS",
			"type": "Earning"
		},
		{
			"salary_component": "Last Salary Deduct",
			"abbr": "NIILS",
			"type": "Deduction"
		}
	]
	for salary_component in salary_components:
		if frappe.db.exists("Salary Component", salary_component["salary_component"]):
			frappe.delete_doc("Salary Component", salary_component["salary_component"], force=True)

		salary_component["salary_component_abbr"] = salary_component["abbr"]
		doc = frappe.new_doc("Salary Component")
		doc.update(salary_component)
		doc.insert()

		set_salary_component_account(doc, company_list)
