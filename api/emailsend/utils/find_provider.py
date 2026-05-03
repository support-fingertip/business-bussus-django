import os
import dns.resolver
import requests

def get_email_provider_from_mx(domain):
    try:
        # Get MX records for the domain
        answers = dns.resolver.resolve(domain, 'MX')
        
        # List of known MX record patterns for major providers
        provider_mx_map = {
            'gmail.com': 'google.com',
            'outlook.com': 'outlook.com',
            'hotmail.com': 'outlook.com',
            'yahoo.com': 'yahoo.com',
            'icloud.com': 'apple.com',
            'zoho.com': 'zoho.com',
            'aol.com': 'aol.com',
        }
        for rdata in answers:
            mail_server = str(rdata.exchange).lower()
            for provider, domain_keyword in provider_mx_map.items():
                if domain_keyword in mail_server:
                    return provider
        # If no known provider is matched
        return "webmail"
    except dns.resolver.NoAnswer:
        return "No MX records found for domain"
    except dns.resolver.NXDOMAIN:
        return "Domain does not exist"
    except Exception as e:
        return str(e)
    
    
def check_domain_authenticated(request):
    url = f"{os.getenv('CPANEL_API_URL')}/sendgrid/check/"
    response = requests.get(
        url,
        headers={
            "Authorization": request.headers.get('Authorization')
        }
    )
    if response.status_code == 200:
        return True
    else:
        return False
    