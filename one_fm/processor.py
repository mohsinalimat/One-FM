import frappe
import requests
import json
from twilio.rest import Client as TwilioClient


@frappe.whitelist()
def sendemail(recipients, subject, header=None, message=None,
        content=None, reference_name=None, reference_doctype=None,
        sender=None, cc=None , attachments=None, delay=None):
    logo = "https://one-fm.com/files/ONEFM_Identity.png"

    frappe.sendmail(template = "default_email",
                    recipients=recipients,
                    sender= sender,
                    cc=cc,
                    reference_name= reference_name,
                    reference_doctype = reference_doctype,
                    subject=subject,
                    args=dict(
                        header=header[0] if header else "",
                        subject=subject,
                        message=message,
                        content=content,
                        logo=logo
                    ),
                    attachments = attachments,
                    delayed=delay)

@frappe.whitelist()
def send_whatsapp(sender_id, body):
	twilio = frappe.get_doc('Twilio Setting' )
	
	client =  TwilioClient(twilio.sid, twilio.token)
	
	message = client.messages.create( 
		from_='whatsapp:' + twilio.t_number,  
		body=body,      
		to= 'whatsapp:+'+ sender_id
	) 
	return message

@frappe.whitelist(allow_guest=True)
def whatsapp():
    request = json.loads(frappe.request.data)
    message = request.form['Body']
    senderId = request.form['From'].split('+')[1]
    
    res = send_whatsapp(senderId=senderId, message=message)

    return '200'