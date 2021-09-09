# class Preparation(Document):
# 	pass
# -*- coding: utf-8 -*-
# Copyright (c) 2021, omar jaber and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import datetime
from frappe.utils import cstr
from frappe.utils import datetime
from frappe.utils import nowdate
from frappe.model.document import Document
from frappe.utils import today, add_days, get_url#extra
from datetime import date, timedelta
import calendar
from datetime import date
from frappe import enqueue
from frappe.utils import get_datetime, add_to_date, getdate, get_link_to_form, now_datetime, nowdate, cstr
from dateutil.relativedelta import relativedelta
from frappe.utils import get_datetime, add_to_date, getdate
from one_fm.grd.doctype.work_permit import work_permit
from one_fm.grd.doctype.medical_insurance import medical_insurance
from one_fm.grd.doctype.residency_payment_request import residency_payment_request
from one_fm.grd.doctype.moi_residency_jawazat import moi_residency_jawazat
from one_fm.grd.doctype.paci import paci
class Preparation(Document):
    def validate(self):
        self.set_grd_values()
        self.set_hr_values()
        # self.set_total_amount()
    
    def set_grd_values(self):
        if not self.grd_supervisor:
            self.grd_supervisor = frappe.db.get_single_value("GRD Settings", "default_grd_supervisor")
        if not self.grd_operator:
            self.grd_operator = frappe.db.get_single_value("GRD Settings", "default_grd_operator")

    def set_hr_values(self):
        if not self.hr_user:
            self.hr_user = frappe.db.get_single_value("Hiring Settings","default_hr_user")

    def on_submit(self):
        self.validate_mandatory_fields_on_submit()
        
        self.db_set('submitted_by', frappe.session.user)
        self.db_set('submitted_on', now_datetime())
        self.recall_create_work_permit_renewal() ## create work permit record for renewals
        self.recall_create_medical_insurance_renewal() # create medical insurance record for renewals
        self.recall_create_moi_renewal_and_extend() # create moi record for all employee
        self.recall_create_paci() # create paci record for all
        self.send_notifications()
        
    def validate_mandatory_fields_on_submit(self):
        # field_list = [{'Renewal or extend':'renewal_or_extend'}, {'Preparation Record':'preparation_record'}]
        mandatory_fields = []
        mandatory_fields_reqd = False
        for item in self.preparation_record:#each item in the preparation_record row
            if not item.renewal_or_extend:#column not filled
                mandatory_fields_reqd = True 
                mandatory_fields.append(item.idx)
        if len(mandatory_fields) > 0:
            message = 'Mandatory fields required in Preparation to Submit<br><br><ul>'
            for mandatory_field in mandatory_fields:
                message += '<li>' +'<p> fill the renewal or extend field for row number {0}</p>''</li>'.format(mandatory_field)
            message += '</ul>'
            frappe.throw(message)

        if self.hr_approval == "No":
            frappe.throw("Must Be Approved By HR ")

    def set_total_amount(self):
        sum = 0
        for item in self.preparation_record:
            if item.total_amount:
                sum+=sum
        self.total_payment = sum

    def recall_create_work_permit_renewal(self):
        work_permit.create_work_permit_renewal(self.name)
    
    def recall_create_medical_insurance_renewal(self):
        medical_insurance.valid_work_permit_exists(self.name)

    def recall_create_moi_renewal_and_extend(self):
        moi_residency_jawazat.set_employee_list_for_moi(self.name)
    
    def recall_create_paci(self):
        paci.create_PACI_renewal(self.name)
  
    def send_notifications(self):
        if self.grd_operator:
            page_link = get_url("/desk#Form/Preparation/" + self.name)
            message = "<p>Renewal Records are created<a href='{0}'>{1}</a>.</p>".format(page_link, self.name)
            subject = 'Renewal Records are created for WP, MI, MOI, PACI'
            send_email(self, [self.grd_operator], message, subject)
            create_notification_log(subject, message, [self.grd_operator], self)

def preparation_monthly_task():
    frappe.enqueue(create_preparation, is_async=True, queue='long')
    

# Calculate the date of the next month (First & Last) (monthly cron in hooks)
def create_preparation():
    doc = frappe.new_doc('Preparation')
    doc.posting_date = nowdate()
    today = date.today()
    first_day = today.replace(day=1) + relativedelta(months=1)
    last_day = first_day.replace(day=calendar.monthrange(first_day.year, first_day.month)[1])
    get_employee_entries(doc,first_day,last_day)
    #doc.save(ignore_permission=True)

#Create list of employee Residency Expiry Date next month
def get_employee_entries(doc,first_day,last_day):
    employee_entries = frappe.db.get_list('Employee',
                            fields=("residency_expiry_date","name"),
                            filters={
                                'residency_expiry_date': ['between',(first_day,last_day)],
                                'status': 'Active',
                                'under_company_residency':['=',1]
                            }
                            )
    employee_entries.sort(key=sort)
    for employee in employee_entries:
        doc.append("preparation_record", {
            "employee": employee.name
        })
    doc.save()
    notify_hr(doc)

#sort list based on residency expriy date
def sort(r):
    return r['residency_expiry_date']

def notify_hr(doc):
    page_link = get_url("/desk#Form/Preparation/" + doc.name)
    subject = ("Preparation Record has been created")
    message = "<p>Kindly, Check and Fill The Renewal and Extend Field for Employees whose Residency Will Expire in the Following month <a href='{0}'></a></p>".format(page_link)
    create_notification_log(subject, message, [doc.hr_user], doc)

def notify_request_for_renewal_or_extend():# Notify finance
    filters = {'docstatus': 1, 'hr_approval': ['=', "Yes"]}
    preparation_list = frappe.get_doc('Preparation', filters,['name', 'notify_finance_user'])
    page_link = get_url("/desk#Form/Preparation/"+preparation_list.name)
    message = "<p>Please Review the Renewal and Extend List of employee {0}<a href='{1}'></a></p>".format(page_link,preparation_list.name)
    subject = '{0} Renewal and Extend list approved'.format("Prepare Payments")
    send_email(preparation_list, [preparation_list.notify_finance_user], message, subject)
    create_notification_log(subject, message, [preparation_list.notify_finance_user], preparation_list)

def send_email(doc, recipients, message, subject):
    frappe.sendmail(
        recipients= recipients,
        subject=subject,
        message=message,
        reference_doctype=doc.doctype,
        reference_name=doc.name
    )

def create_notification_log(subject, message, for_users, reference_doc):
    for user in for_users:
        doc = frappe.new_doc('Notification Log')
        doc.subject = subject
        doc.email_content = message
        doc.for_user = user
        doc.document_type = reference_doc.doctype
        doc.document_name = reference_doc.name
        doc.from_user = reference_doc.modified_by
        doc.insert(ignore_permissions=True)


