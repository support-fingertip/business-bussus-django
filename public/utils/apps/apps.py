import json
from django.db import connection, transaction
from psycopg2.extras import Json

# {"name": "event", "type": "object"}, removed from apps.json

def load_apps():
    with open('public/utils/apps/apps.json') as f:
        return json.load(f)

def create_app(USER_ID, schema, user_name=None):
    apps = load_apps()

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO %s;", [schema])

                for app in apps:

                    insert_params = {
                        'disable_end_user_personalisation': app['disable_end_user_personalisation'],
                        'disable_temporary_tabs': app['disable_temporary_tabs'],
                        'use_app_image_color_for_org_theme': app['use_app_image_color_for_org_theme'],
                        'use_omni_channel_sidebar': app['use_omni_channel_sidebar'],
                        'description': app['description'],
                        'name': app['name'],
                        'label': app['label'],
                        'tabs': Json(app['tabs']),   # <- only if column is json/jsonb
                        'developer': user_name if app['name'] == 'sales' and user_name else app['developer'],
                        'setup_experiance': app['setup_experiance'],
                        'navigation_style': app['navigation_style'],
                        'form_factor': app['form_factor'],
                        'color': app['color'],
                        'image': app['image'],
                        'created_by_id': USER_ID,
                        'last_modified_by_id': USER_ID,
                        'owner_id': USER_ID,
                        'organisation': app['organisation'],
                        'logo': app['logo'],
                        'utility_bar': app['utility_bar'],
                        'default_landing_tab': app['default_landing_tab'],
                        'organisation_id': None   # safer than empty string
                    }

                    insert_sql = """
                        INSERT INTO app (
                            disable_end_user_personalisation, disable_temporary_tabs, use_app_image_color_for_org_theme,
                            use_omni_channel_sidebar, description, name,
                            label, tabs, developer,
                            setup_experiance, navigation_style, form_factor,
                            color, image, created_by_id,
                            last_modified_by_id, owner_id, organisation,
                            logo, utility_bar, default_landing_tab,
                            organisation_id, created_date, last_modified_date
                        )
                        VALUES (
                            %(disable_end_user_personalisation)s, %(disable_temporary_tabs)s, %(use_app_image_color_for_org_theme)s,
                            %(use_omni_channel_sidebar)s, %(description)s, %(name)s,
                            %(label)s, %(tabs)s, %(developer)s,
                            %(setup_experiance)s, %(navigation_style)s, %(form_factor)s,
                            %(color)s, %(image)s, %(created_by_id)s,
                            %(last_modified_by_id)s, %(owner_id)s, %(organisation)s,
                            %(logo)s, %(utility_bar)s, %(default_landing_tab)s,
                            %(organisation_id)s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        RETURNING id;
                    """

                    cursor.execute(insert_sql, insert_params)
                    app_id = cursor.fetchone()[0]

                    cursor.execute("SELECT id FROM profile;")
                    profiles = cursor.fetchall()

                    permissions = [(pid[0], app_id, True) for pid in profiles]

                    cursor.executemany(
                        "INSERT INTO app_permissions (profile_id, app_id, access) VALUES (%s, %s, %s)",
                        permissions
                    )

        return True

    except Exception as e:
        raise Exception(str(e))