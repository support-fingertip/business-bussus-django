from django.db import connection
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
import re
import os

class SuggestionDomainView(APIView):
    authentication_classes = []  # Disable authentication for this view
    permission_classes = [AllowAny]  # Allow any user to access this view

    def get(self, request, table_name=None):
        name = request.GET.get('name')
        
        # Replace spaces with dashes and convert to lowercase
        replace_name = name.replace(" ", "-").lower()
        
        cursor = connection.cursor()
        
        # First, check if the exact domain already exists in the database
        query = f"SELECT domain FROM organizations WHERE LOWER(domain) = %s;"
        try:
            cursor.execute(query, [replace_name])
            exists = cursor.fetchone()

            if exists:
                # If the domain already exists, generate a unique domain using suffix logic
                base_name, extension = self._extract_base_and_extension(replace_name)
                new_domain = self._generate_unique_domain(cursor, base_name, extension)
                return Response({"suggestion": new_domain}, status=status.HTTP_200_OK)
            else:
                # If the domain does not exist, suggest the base domain name
                return Response({"suggestion": replace_name}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _extract_base_and_extension(self, domain):
        """
        Extracts the base name and extension from the domain.
        For example: 'example.com' -> ('example', '.com')
        """
        match = re.match(r'^(.*?)(\.[a-z]{2,6})$', domain)
        if match:
            base_name = match.group(1)
            extension = match.group(2)
        else:
            base_name = domain
            extension = ""
        
        return base_name, extension

    def _generate_unique_domain(self, cursor, base_name, extension):
        """
        Generates a unique domain by adding a suffix to the base name and checking if it exists.
        The suffix is derived from the first 3 characters of the base name.
        """
        suffix = base_name[:3]  # Take the first 3 characters of the base name (e.g., 'exa' from 'example')

        # Check if the domain with the suffix already exists
        new_domain = f"{base_name}-{suffix}{extension}"
        i = 1
        query = f"SELECT domain FROM organizations WHERE LOWER(domain) = %s;"
        
        while True:
            cursor.execute(query, [new_domain.lower()])
            exists = cursor.fetchone()
            if exists:
                # If the domain exists, increment the suffix and check again
                new_domain = f"{base_name}-{suffix}{i}{extension}"
                i += 1
            else:
                # Return the unique domain
                return new_domain


class SuggestionUsernameView(APIView):
    authentication_classes = []  # Disable authentication for this view
    permission_classes = [AllowAny]  # Allow any user to access this view

    def get(self, request):
        email = request.GET.get('email')
        try:
            # unique_username = generate_unique_username(email)
            data = requests.get(f"{os.getenv('CPANEL_API_URL')}/auth/suggest/username/?email={email}")
            unique_username = data.json().get("suggestion")
            return Response({"suggestion": unique_username}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




def generate_unique_username(email):
    """
    Generates a unique username based on the provided email by appending a suffix if necessary.
    The username will be derived from the email's local part (before '@').

    :param cursor: Database cursor to interact with the database.
    :param email: The email provided by the user.
    :return: A unique username.
    """
    cursor = connection.cursor()

    # Check if the exact username exists in the database
    query = f"SELECT username FROM users WHERE LOWER(email) = %s;"
    cursor.execute(query, [email.lower()])
    exists = cursor.fetchone()

    if not exists:
        # If the username does not exist, return it as is
        return email

    # If the username already exists, generate a unique username by appending a suffix
    i = 1
    local_part = email.split('@')[0]
    last_part = email.split('@')[1]
    new_username = f"{local_part}.{i}"
    cursor.execute(query, [new_username.lower()])
    exists = len(cursor.fetchall()) > 0
    while exists:
        i += 1
        new_username = f"{local_part}.{i}"
        cursor.execute(query, [new_username.lower()])
        exists = len(cursor.fetchall()) > 0
        if not exists:
            return new_username+"@"+last_part
    return new_username+"@"+last_part

        # cursor.execute(query, [new_username.lower()])
        # exists = cursor.fetchone()
        # if not exists:
        #     data = False
        #     return new_username+"@"+last_part

# def replace_special_characters(username):

class CheckUsernameExistsView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]  
    def get(self, request):
        username = request.GET.get('username')
        try:
            cursor = connection.cursor()
            query = f"SELECT COUNT(*) FROM users WHERE LOWER(username) = %s;"
            cursor.execute(query, [username.lower()])
            count = cursor.fetchone()[0]
            if count > 0 :
                return Response({"exists": True}, status=status.HTTP_200_OK)
            else:
                return Response({"exists": False}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)