from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.db import connection
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from django.conf import settings
import os
from datetime import datetime
import sys
from version2.settings import BASE_DIR

@method_decorator(csrf_exempt, name='dispatch')
class ExistsView(APIView):
    authentication_classes = []  # Disable authentication for this view
    permission_classes = [AllowAny]  # Allow any user to access this view
    def get(self, request, table_name=None):       
        # table_name = request.GET.get('table')
        field_name = request.GET.get('field')
        value = str(request.GET.get('value'))
        
        if not table_name or not field_name or value is None:
            return Response({"error": "Missing required parameters."}, status=status.HTTP_400_BAD_REQUEST)
        if table_name not in ['users', 'organizations']:
            return Response({"error": "Table not allowed."}, status=status.HTTP_400_BAD_REQUEST)
        cursor = connection.cursor()        
        query = f"SELECT EXISTS(SELECT 1 FROM {table_name} WHERE LOWER({field_name}) = %s);"
        try:
            cursor.execute(query, [value.lower()])
            exists = cursor.fetchone()[0]
            return Response({"exists": True if exists else False}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        



def error_record(er)->dict:
    try:
        file = str(settings.BASE_DIR) +"/error_log.txt"
        if not os.path.isfile(file):
            open( f"{BASE_DIR}/error_log.txt","x")
        errorlog = open(f"{BASE_DIR}/error_log.txt","a")
        error = str(er)
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        currnet_date_time = datetime.now().strftime("%d-%m-%Y %I:%m %p")
        errorlog.write(f"\n Error-> Date:{currnet_date_time} Filename:{fname}, Linenumber:{exc_tb.tb_lineno},Error Type:{type(er)} Error:{str(error)}")
        errorlog.close()
        return {"msg":str(er),"err_type":type(er)}
    except Exception as er:
        print(er)
        return None
    

        