from django.urls import path
from .views import export_selected_objects,export_audit_trail, export_report_excel

app_name = "data_export"  # This must be defined

urlpatterns = [
    path("exportdata/", export_selected_objects, name="export_data"),
    path("export_audit_trail/", export_audit_trail, name="export_audit_trail"),
    path("export_report_excel", export_report_excel, name="export_report_excel"),
]
