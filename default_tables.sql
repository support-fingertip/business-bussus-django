
CREATE TABLE app (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('apP_', LEFT(gen_random_uuid()::text, 12)),
    disable_end_user_personalisation BOOLEAN NOT NULL DEFAULT FALSE,
    disable_temporary_tabs BOOLEAN NOT NULL DEFAULT FALSE,
    use_app_image_color_for_org_theme BOOLEAN NOT NULL DEFAULT FALSE,
    use_omni_channel_sidebar BOOLEAN NOT NULL DEFAULT FALSE,
    description VARCHAR(1024),
    name VARCHAR(255) NOT NULL UNIQUE,
    label VARCHAR(256) NOT NULL DEFAULT 'Unknown',
    tabs JSONB,
    developer VARCHAR(255),
    setup_experiance VARCHAR(255),
    navigation_style VARCHAR(255),
    form_factor VARCHAR(255),
    color VARCHAR(7),
    image VARCHAR(1023),
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    organisation VARCHAR(225),
    last_modified_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    logo VARCHAR(2048),
    utility_bar TEXT,
    default_landing_tab VARCHAR(255),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    organisation_id VARCHAR(64),
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL
);


CREATE TABLE IF NOT EXISTS app_permissions (
    id VARCHAR(64) PRIMARY KEY DEFAULT concat('apPEr_', "left"((gen_random_uuid())::text, 64)),
    access BOOLEAN NOT NULL,
    app_id VARCHAR(64) NOT NULL REFERENCES app(id) ON DELETE CASCADE,
    profile_id VARCHAR(64) NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL
);


CREATE TABLE object (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('ObCt_', LEFT(gen_random_uuid()::text, 12)),
    allow_activities BOOLEAN NOT NULL DEFAULT FALSE,
    allow_bulk_api_access BOOLEAN NOT NULL DEFAULT FALSE,
    allow_in_chatter_groups BOOLEAN NOT NULL DEFAULT FALSE,
    allow_reports BOOLEAN NOT NULL DEFAULT FALSE,
    allow_sharing BOOLEAN NOT NULL DEFAULT FALSE,
    allow_streaming_api_access BOOLEAN NOT NULL DEFAULT FALSE,
    setup BOOLEAN NOT NULL DEFAULT FALSE,
    datatype VARCHAR(255),
    icon VARCHAR(255),
    icon_color VARCHAR(10),
    deployment_status VARCHAR(255),
    description TEXT,
    enable_licensing BOOLEAN NOT NULL DEFAULT FALSE,
    label VARCHAR(255),
    name VARCHAR(255) NOT NULL UNIQUE,
    plural_label VARCHAR(255),
    record_name VARCHAR(255),
    search_status BOOLEAN NOT NULL DEFAULT FALSE,
    show_tab BOOLEAN NOT NULL DEFAULT TRUE,
    starts_with_vowel_sound BOOLEAN NOT NULL DEFAULT FALSE,
    track_field_history BOOLEAN NOT NULL DEFAULT FALSE,
    prefix VARCHAR(10),
    default_access_level VARCHAR(20) DEFAULT 'Private',
    type VARCHAR(50) NOT NULL DEFAULT 'Custom',
    display_format VARCHAR(255),
    starting_number INTEGER,
    

    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    organisation VARCHAR(64) REFERENCES public.organizations(id) ON DELETE SET NULL,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL
);


CREATE TABLE IF NOT EXISTS tab_permissions (
    id VARCHAR(64) PRIMARY KEY DEFAULT concat('tBpEr_', "left"((gen_random_uuid())::text, 18)),
    type VARCHAR(64),
    profile_id VARCHAR(64) REFERENCES profile(id) ON DELETE CASCADE,
    object_id VARCHAR(64) REFERENCES object(id) ON DELETE CASCADE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS object_permissions (
    id VARCHAR(64) PRIMARY KEY DEFAULT concat('obPer', "left"((gen_random_uuid())::text, 18)),
    read BOOLEAN NOT NULL,
    write BOOLEAN NOT NULL,
    edit BOOLEAN NOT NULL,
    delete BOOLEAN NOT NULL,
    view_all BOOLEAN NOT NULL,
    modify_all BOOLEAN NOT NULL,
    object_id VARCHAR(64) NOT NULL REFERENCES object(id) ON DELETE CASCADE,
    profile_id VARCHAR(64) NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS page_layouts (
    id VARCHAR(64) PRIMARY KEY DEFAULT concat('pGl_', "left"((gen_random_uuid())::text, 18)),
    object_name VARCHAR(255) NOT NULL,
    object_id VARCHAR(64) REFERENCES object(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    label VARCHAR(255) NOT NULL,
    sections JSONB NOT NULL,
    layout JSONB,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by VARCHAR(255),
    buttons JSONB,
    related_lists JSONB DEFAULT '[]'::jsonb,
    CONSTRAINT unique_page_layout_name_per_object UNIQUE (name, object_name)
);

CREATE TABLE search_layouts (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('sRcHL_', LEFT(gen_random_uuid()::text, 12)),
    object_id VARCHAR(64) NOT NULL,
    search_results_fields JSONB,
    lookup_dialog_fields JSONB,
    recent_items_fields JSONB,

    created_by_id VARCHAR(255),
    last_modified_by_id VARCHAR(255),
    owner_id VARCHAR(255),
    created_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    organisation VARCHAR(225),

    CONSTRAINT fk_search_layout_object FOREIGN KEY (object_id) REFERENCES object(id) ON DELETE CASCADE,
    CONSTRAINT fk_search_layout_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_search_layout_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_search_layout_owner FOREIGN KEY (owner_id) REFERENCES public.users(id)
);

CREATE TABLE IF NOT EXISTS field_mapping(
	id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('fMp_', LEFT(gen_random_uuid()::TEXT, 16)),
	object_id VARCHAR(64) REFERENCES object(id) ON DELETE CASCADE,
	mapped_with VARCHAR(64) REFERENCES object(id) ON DELETE CASCADE,
	mapped_fields JSONB DEFAULT '{}',
	created_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
	last_modified_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
	created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
	last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL	
);

CREATE TABLE sharing_records (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('sHreC_', LEFT(gen_random_uuid()::text, 12)),
    object_id VARCHAR(64),
    record_id VARCHAR(64),
    user_id VARCHAR(64),
    access_level VARCHAR(32) NOT NULL DEFAULT 'Public Read Write',
    reason VARCHAR(64) NOT NULL DEFAULT 'Ownership',
    hierarchy_access BOOLEAN DEFAULT FALSE,

    created_by_id VARCHAR(255),
    last_modified_by_id VARCHAR(255),
    owner_id VARCHAR(255),
    created_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    organisation VARCHAR(225),
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,

    CONSTRAINT fk_sharing_object FOREIGN KEY (object_id) REFERENCES object(id) ON DELETE CASCADE,
    CONSTRAINT fk_sharing_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_sharing_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_sharing_owner FOREIGN KEY (owner_id) REFERENCES public.users(id),

    CONSTRAINT unique_record_user UNIQUE (record_id, user_id)
);

CREATE INDEX idx_sharing_record_id ON sharing_records(record_id);
CREATE INDEX idx_sharing_user_id ON sharing_records(user_id);

CREATE TABLE fields (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('fIld_', LEFT(gen_random_uuid()::text, 12)),
    required BOOLEAN DEFAULT FALSE,
    unique_field BOOLEAN DEFAULT FALSE,
    external_id BOOLEAN DEFAULT FALSE,
    custom_report_type BOOLEAN DEFAULT FALSE,
    custom_field BOOLEAN DEFAULT FALSE,
    ai_prediction BOOLEAN DEFAULT FALSE,
    auto_number BOOLEAN DEFAULT FALSE,
    help_text TEXT,
    display_format VARCHAR(255),
    starting_number INTEGER,
    default_value_in_checkbox VARCHAR(64) DEFAULT 'unchecked',
    pickup_values TEXT[],  -- changed to text array
    decimal_places INTEGER,
    default_value VARCHAR(255),
    geolocation_notation VARCHAR(255),
    mask_type VARCHAR(255),
    mask_character VARCHAR(255),
    visible_lines INTEGER,
    number_length INTEGER,
    datatype VARCHAR(255),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    help TEXT,
    length INTEGER,
    object_name VARCHAR(255),
    object_id VARCHAR(64),
    label VARCHAR(255),
    on_delete VARCHAR(255),
    parent_object VARCHAR(255),
    relationship_name TEXT,
    is_modifiable BOOLEAN DEFAULT TRUE,
    created_by_id VARCHAR(255),
    last_modified_by_id VARCHAR(255),
    owner_id VARCHAR(255),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    no_skip Boolean DEFAULT FALSE,
    no_rollback Boolean DEFAULT FALSE,

    sort_alpha BOOLEAN DEFAULT FALSE,
    first_as_default BOOLEAN DEFAULT FALSE,
    limit_predefined_values BOOLEAN DEFAULT FALSE,
    send_mail BOOLEAN DEFAULT FALSE,

    -- Formula field columns
    formula_expression TEXT,
    formula_return_type VARCHAR(50),

    -- Roll-up summary columns
    summarized_object VARCHAR(255),
    rollup_type VARCHAR(20),
    field_to_aggregate VARCHAR(255),
    filter_criteria JSONB,

    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    
    organisation_id VARCHAR(64) REFERENCES public.organizations(id) ON DELETE CASCADE,

    CONSTRAINT fk_fields_object FOREIGN KEY (object_id) REFERENCES object(id) ON DELETE CASCADE,
    CONSTRAINT fk_fields_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_fields_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_fields_owner FOREIGN KEY (owner_id) REFERENCES public.users(id),

    CONSTRAINT unique_name_object UNIQUE (name, object_id)
);

CREATE TABLE IF NOT EXISTS field_permissions (
    id VARCHAR(64) PRIMARY KEY DEFAULT ('peFld_'::text || "left"((gen_random_uuid())::text, 18)),
    read_only BOOLEAN NOT NULL,
    visible BOOLEAN NOT NULL,
    edit_access BOOLEAN NOT NULL,
    read_access BOOLEAN NOT NULL,
    fields_id VARCHAR(64) NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    object_id VARCHAR(64) NOT NULL REFERENCES object(id) ON DELETE CASCADE,
    profile_id VARCHAR(64) NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);



CREATE TABLE listviews (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('lsTvW_', LEFT(gen_random_uuid()::text, 12)),
    object_id VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    label VARCHAR(255) NOT NULL,
    is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
    filters JSONB,
    filter_logic VARCHAR(1024),
    visible_columns JSONB,

    created_by_id VARCHAR(255),
    last_modified_by_id VARCHAR(255),
    owner_id VARCHAR(255),
    created_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    organisation VARCHAR(225),
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,

    CONSTRAINT fk_listviews_object FOREIGN KEY (object_id) REFERENCES object(id) ON DELETE CASCADE,
    CONSTRAINT fk_listviews_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_listviews_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_listviews_owner FOREIGN KEY (owner_id) REFERENCES public.users(id),

    CONSTRAINT unique_name_object_listview UNIQUE (name, object_id)
);

CREATE TABLE report_folder (
    id VARCHAR(64) NOT NULL DEFAULT concat('fldr_', left(gen_random_uuid()::text, 12)),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    visibility VARCHAR(20) DEFAULT 'private',
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT now(),
    last_modified_date TIMESTAMP DEFAULT now(),
    is_deleted BOOLEAN DEFAULT FALSE,
    organisation_id VARCHAR(64) REFERENCES public.organizations(id) ON DELETE CASCADE,
    parent_id VARCHAR(64) REFERENCES report_folder(id) ON DELETE CASCADE,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,

    CONSTRAINT report_folder_pkey PRIMARY KEY (id),
    CONSTRAINT report_folder_name_key UNIQUE (name)
);


CREATE TABLE report (
    id VARCHAR(64) NOT NULL DEFAULT concat('Rpt_', left(gen_random_uuid()::text, 12)),
    name VARCHAR(255) NOT NULL,
    report_type VARCHAR(500),
    fields JSONB,
    filters JSONB,
    filter_logic TEXT,
    filter_json JSONB,
    group_by JSONB,
    created_by_id TEXT,
    folder_id TEXT,
    created_date TIMESTAMP DEFAULT now(),
    last_modified_date TIMESTAMP DEFAULT now(),
    table_name TEXT,
    is_deleted BOOLEAN DEFAULT FALSE,

    -- NEW toggle fields for report options
    show_row_counts BOOLEAN DEFAULT TRUE,
    show_detail_rows BOOLEAN DEFAULT TRUE,
    show_subtotals BOOLEAN DEFAULT TRUE,
    show_grand_total BOOLEAN DEFAULT TRUE,

    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,

    CONSTRAINT report_pkey PRIMARY KEY (id),

    CONSTRAINT fk_created_by_id FOREIGN KEY (created_by_id)
        REFERENCES public.users (id)
        ON DELETE SET NULL,

    CONSTRAINT fk_folder FOREIGN KEY (folder_id)
        REFERENCES report_folder (id)
        ON DELETE CASCADE
);

CREATE TABLE dashboard_folders (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('dF_', LEFT(gen_random_uuid()::TEXT, 12)),
    name VARCHAR(255) NOT NULL,
    label VARCHAR(255) NOT NULL,
    description TEXT DEFAULT NULL,
    parent_id VARCHAR(64),
    created_by_id VARCHAR(255),
    last_modified_by_id VARCHAR(255),
    owner_id VARCHAR(255),
    created_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    organisation VARCHAR(225),
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,

    CONSTRAINT fk_folder_created_by FOREIGN KEY (created_by_id)
        REFERENCES public.users (id)
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,

    CONSTRAINT fk_folder_last_modified_by FOREIGN KEY (last_modified_by_id)
        REFERENCES public.users (id)
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,

    CONSTRAINT fk_folder_owner FOREIGN KEY (owner_id)
        REFERENCES public.users (id)
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,

    CONSTRAINT fk_folder_parent FOREIGN KEY (parent_id)
        REFERENCES dashboard_folders (id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE
);

CREATE TABLE dashboard (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('dB_', LEFT(gen_random_uuid()::text, 12)),
    name VARCHAR(255) NOT NULL,
    created_by VARCHAR(255),
    last_modified_by VARCHAR(255),
    created_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    components JSONB,
    folder_name VARCHAR(255),
    running_user VARCHAR(255),
    dashboard_type VARCHAR(100),
    grid_layout JSONB,
    refresh_frequency VARCHAR(100),
    layout JSONB,
    description VARCHAR(256),
    created_by_id VARCHAR,
    folder_id VARCHAR(64),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,

    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,

    CONSTRAINT dashboard_name_key UNIQUE (name),
    CONSTRAINT fk_dashboard_created_by FOREIGN KEY (created_by_id)
        REFERENCES public.users(id)
        ON UPDATE NO ACTION
        ON DELETE SET NULL,

    CONSTRAINT fk_dashboard_folder_id FOREIGN KEY (folder_id)
        REFERENCES dashboard_folders(id)
        ON UPDATE NO ACTION
        ON DELETE SET NULL
);

CREATE TABLE dashboard_component (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('dC_', LEFT(gen_random_uuid()::text, 12)),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    data_source VARCHAR(255),
    filters JSONB,
    metric_config JSONB,
    chart_config JSONB,
    geometry JSONB,
    created_date TIMESTAMP DEFAULT now(),
    filter_logic TEXT,
    chart_data JSONB,
    report_id VARCHAR(255),
    widget_settings JSONB,
    listview_id VARCHAR(64),
    dashboard_id VARCHAR(255),
    CONSTRAINT component_name_key UNIQUE (name),
    CONSTRAINT fk_dashboard FOREIGN KEY (dashboard_id)
        REFERENCES dashboard(id)
        ON UPDATE NO ACTION
        ON DELETE SET NULL,
    CONSTRAINT fk_report FOREIGN KEY (report_id)
        REFERENCES report(id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE
);


CREATE TABLE page_builder (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('pGbL_', LEFT(gen_random_uuid()::text, 12)),
    name VARCHAR(255) NOT NULL UNIQUE,
    description VARCHAR(255),
    folder_name VARCHAR(255),
    type VARCHAR(100),
    layout JSONB,
    refresh_frequency VARCHAR(100),
    created_by_id VARCHAR(255),
    last_modified_by_id VARCHAR(255),
    owner_id VARCHAR(255),
    created_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    organisation VARCHAR(225),
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,

    CONSTRAINT fk_dashboard_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_dashboard_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_dashboard_owner FOREIGN KEY (owner_id) REFERENCES public.users(id)
);

CREATE TABLE page_component (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('pGcoP_', LEFT(gen_random_uuid()::text, 12)),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    data_source VARCHAR(255),
    listview_id VARCHAR(255),
    page_builder_id VARCHAR(64) REFERENCES page_builder(id) ON DELETE CASCADE,
    dashboard_component_id VARCHAR(64) REFERENCES dashboard_component(id) ON DELETE CASCADE,
    filters JSONB,
    metric_config JSONB,
    chart_config JSONB,
    geometry JSONB,
    created_by_id VARCHAR(255),
    last_modified_by_id VARCHAR(255),
    owner_id VARCHAR(255),
    created_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    organisation VARCHAR(225),
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,

    CONSTRAINT fk_component_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_component_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_component_owner FOREIGN KEY (owner_id) REFERENCES public.users(id)
);

CREATE TABLE page_builder_assignment (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('pBAsn_', LEFT(gen_random_uuid()::text, 12)),
    profile_id VARCHAR(64) NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    page_builder_id VARCHAR(64) NOT NULL REFERENCES page_builder(id) ON DELETE CASCADE,
	created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64), -- Foreign key to User table
    last_modified_by_id VARCHAR(64), -- Foreign key to User table
    CONSTRAINT fk_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id)	
);

CREATE TABLE layout_assignment (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('plAsn_', LEFT(gen_random_uuid()::text, 12)),

    profile_id VARCHAR(64) NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    object_id VARCHAR(64) NOT NULL REFERENCES object(id) ON DELETE CASCADE,
    page_layouts_id VARCHAR(64) NOT NULL REFERENCES page_layouts(id) ON DELETE CASCADE,
    record_type TEXT DEFAULT 'default',
	created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64), -- Foreign key to User table
    last_modified_by_id VARCHAR(64), -- Foreign key to User table
    CONSTRAINT fk_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id)
	
);



CREATE TABLE workflow (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('wF-', LEFT(gen_random_uuid()::text, 12)), -- Adds 'WF-' as the prefix and limits the UUID to 12 characters
    name VARCHAR(255) NOT NULL,
    trigger_type VARCHAR(20) DEFAULT 'create',
    module_name VARCHAR(100),
    description TEXT,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64), -- Foreign key to User table
    last_modified_by_id VARCHAR(64), -- Foreign key to User table
    CONSTRAINT fk_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id)
);

CREATE TABLE IF NOT EXISTS path_builder(
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('pBl_', LEFT(gen_random_uuid()::text, 12)), -- Adds 'ND-' as the prefix and limits the UUID to 12 characters
    name VARCHAR(255) NOT NULL UNIQUE,
    label VARCHAR(255),
	object_id VARCHAR(64) REFERENCES object(id) ON DELETE SET NULL,
	field_id VARCHAR(64) REFERENCES fields(id) ON DELETE SET NULL,
	stages JSONB,
	is_active BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    organisation_id VARCHAR(64) REFERENCES public.organizations(id) ON DELETE SET NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE TABLE workflow_node (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('wfND-', LEFT(gen_random_uuid()::text, 12)), -- Adds 'ND-' as the prefix and limits the UUID to 12 characters
    workflow_id VARCHAR(64), -- Foreign key to Workflow table
    label VARCHAR(255) NOT NULL,
    type VARCHAR(64) DEFAULT 'standard',
    node_type VARCHAR(50) NOT NULL,
    position JSONB DEFAULT '{}'::jsonb,
    data JSONB DEFAULT '{}'::jsonb,
    measured JSONB DEFAULT '{}'::jsonb,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64), -- Foreign key to User table
    last_modified_by_id VARCHAR(64), -- Foreign key to User table
    CONSTRAINT fk_workflow FOREIGN KEY (workflow_id) REFERENCES workflow(id) ON DELETE CASCADE,
    CONSTRAINT fk_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id)
);


CREATE TABLE workflow_edge (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('wfED-', LEFT(gen_random_uuid()::text, 12)), -- Adds 'ED-' as the prefix and limits the UUID to 12 characters
    workflow_id VARCHAR(64), -- Foreign key to Workflow table
    source_id VARCHAR(64), -- Foreign key to Node table (source)
    target_id VARCHAR(64), -- Foreign key to Node table (target)
    source_handle VARCHAR(50),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64), -- Foreign key to User table
    last_modified_by_id VARCHAR(64), -- Foreign key to User table
    is_deleted BOOLEAN DEFAULT FALSE,
    CONSTRAINT fk_workflow FOREIGN KEY (workflow_id) REFERENCES workflow(id) ON DELETE CASCADE,
    CONSTRAINT fk_source FOREIGN KEY (source_id) REFERENCES workflow_node(id),
    CONSTRAINT fk_target FOREIGN KEY (target_id) REFERENCES workflow_node(id),
    CONSTRAINT fk_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id)
);

CREATE TABLE telephony_config (
    id VARCHAR(64) NOT NULL DEFAULT CONCAT('tePc_', LEFT(gen_random_uuid()::TEXT, 12)),
    provider VARCHAR(50),
    target_object VARCHAR(100),
    target_field VARCHAR(100),
    display_fields TEXT[],
    disposition_values TEXT[],
    status BOOLEAN DEFAULT TRUE,
    authtoken VARCHAR,
    sid VARCHAR,
    CONSTRAINT telephony_config_pkey PRIMARY KEY (id),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE TABLE user_group (
    id VARCHAR(64) NOT NULL DEFAULT CONCAT('uGrP_', LEFT(gen_random_uuid()::TEXT, 12)),
    label VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_by_id VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    grant_access_using_hierarchy BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMP DEFAULT now(),

    CONSTRAINT user_group_pkey PRIMARY KEY (id),
    CONSTRAINT user_group_name_key UNIQUE (name),
    CONSTRAINT user_group_created_by_fkey FOREIGN KEY (created_by_id)
        REFERENCES public.users (id) ON DELETE SET NULL,
    CONSTRAINT user_group_modified_by_fkey FOREIGN KEY (last_modified_by_id)
        REFERENCES public.users (id) ON DELETE SET NULL
);


CREATE TABLE user_group_users (
    id VARCHAR(64) NOT NULL DEFAULT CONCAT('uGus_', LEFT(gen_random_uuid()::TEXT, 12)),
    user_group_id TEXT NOT NULL,
    user_id VARCHAR NOT NULL,
    created_date TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    
    -- Constraints
    CONSTRAINT user_group_users_pkey PRIMARY KEY (id),
    CONSTRAINT user_group_users_user_group_id_user_id_key UNIQUE (user_group_id, user_id),
    CONSTRAINT user_group_users_user_group_id_fkey FOREIGN KEY (user_group_id)
        REFERENCES user_group (id) ON DELETE CASCADE,
    CONSTRAINT user_group_users_user_id_fkey FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
);


CREATE TABLE user_group_profiles (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('ugP_', LEFT(gen_random_uuid()::TEXT, 12)),
    user_group_id VARCHAR NOT NULL,
    profile_id VARCHAR NOT NULL,
    created_date TIMESTAMP DEFAULT now(),

    FOREIGN KEY (user_group_id) REFERENCES user_group(id) ON DELETE CASCADE,
    FOREIGN KEY (profile_id) REFERENCES profile(id) ON DELETE CASCADE,

    UNIQUE(user_group_id, profile_id)
);


CREATE TABLE user_group_public_groups (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('ugPg_', LEFT(gen_random_uuid()::TEXT, 12)),
    user_group_id VARCHAR NOT NULL,
    public_group_id VARCHAR NOT NULL,
    created_date TIMESTAMP DEFAULT now(),

    FOREIGN KEY (user_group_id) REFERENCES user_group(id) ON DELETE CASCADE,
    FOREIGN KEY (public_group_id) REFERENCES user_group(id) ON DELETE CASCADE,

    UNIQUE(user_group_id, public_group_id)
);

CREATE TABLE landing_numbers (
    id VARCHAR(64) NOT NULL DEFAULT CONCAT('lDnbr_', LEFT(gen_random_uuid()::TEXT, 12)),
    telephony_id VARCHAR(100),
    landing_number VARCHAR(20),
    group_name VARCHAR(100),
    routing_logic VARCHAR(20),
    status BOOLEAN DEFAULT TRUE,
    group_id TEXT,
    CONSTRAINT landing_numbers_pkey PRIMARY KEY (id),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE TABLE user_gmail_tokens (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('ugTok_', LEFT(gen_random_uuid()::text, 12)),
    user_id VARCHAR NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    token_type TEXT,
    expires_in INTEGER,
    expiry_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT unique_user_id UNIQUE(user_id)
);


CREATE TABLE user_outlook_tokens (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('uOTok_', LEFT(gen_random_uuid()::text, 12)),
    user_id VARCHAR NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    token_type TEXT,
    expires_in INTEGER,
    expiry_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Foreign key constraint
    CONSTRAINT fk_user_outlook FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE,
    -- Unique constraint on user_id
    CONSTRAINT unique_outlook_user_id UNIQUE(user_id)
);



CREATE TABLE dashboard_folder_sharing (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('dfsh_', LEFT(gen_random_uuid()::text, 12)),
    folder_id VARCHAR(64) NOT NULL,
    shared_with_type VARCHAR(50) NOT NULL,  -- 'user' or 'profile', no CHECK constraint
    shared_with_id VARCHAR(64) NOT NULL,
    access_level VARCHAR(50) NOT NULL,      -- 'view' or 'manage', no CHECK constraint

    created_by_id VARCHAR(255),
    created_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    last_modified_by_id VARCHAR(255),
    last_modified_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    organisation VARCHAR(225),
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,

    -- Foreign Keys
    CONSTRAINT fk_dfsh_folder FOREIGN KEY (folder_id) REFERENCES dashboard_folders(id),
    CONSTRAINT fk_dfsh_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_dfsh_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id)
);

CREATE TABLE email_templates (
    id TEXT NOT NULL DEFAULT ('TPL-' || gen_random_uuid()),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    available_for_use BOOLEAN DEFAULT TRUE,
    template_type VARCHAR(10) DEFAULT 'text',
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    author_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    selected_object VARCHAR(64) REFERENCES object(id) ON DELETE SET NULL,
    record_id VARCHAR(255),
    created_date TIMESTAMP DEFAULT now(),
    sendgrid_template_id VARCHAR(255),
    sendgrid_template_hash VARCHAR(64),
    CONSTRAINT email_templates_pkey PRIMARY KEY (id),
    CONSTRAINT email_templates_name_key UNIQUE (name),
    CONSTRAINT fk_author FOREIGN KEY (author_id)
        REFERENCES public.users (id)
        ON DELETE SET NULL
);

CREATE TABLE email_provider_setup (
    id VARCHAR(64) NOT NULL DEFAULT CONCAT('eprov_', LEFT(gen_random_uuid()::TEXT, 12)),
    user_id VARCHAR(64) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    cred jsonb,
    created_date TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT email_provider_setup_pkey PRIMARY KEY (id),
    CONSTRAINT email_provider_setup_user_id_key UNIQUE (user_id),
    CONSTRAINT fk_email_user FOREIGN KEY (user_id)
        REFERENCES public.users (id)
        ON UPDATE NO ACTION
        ON DELETE CASCADE,
    CONSTRAINT email_provider_setup_provider_check CHECK (
        provider IN ('gmail', 'outlook', 'sendgrid')
    )
);



CREATE TABLE audit_trail_track (
    id VARCHAR(64) NOT NULL DEFAULT CONCAT('aTtr_', LEFT(gen_random_uuid()::TEXT, 12)),
    source_namespace_prefix VARCHAR(100),
    action TEXT NOT NULL,
    section VARCHAR(100) NOT NULL,
    is_delegate_user BOOLEAN NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL,
    user_id VARCHAR(64),
    created_date TIMESTAMP DEFAULT now(),

    CONSTRAINT audit_trail_track_user_id_fk FOREIGN KEY (user_id)
        REFERENCES public.users(id)
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
);

CREATE TABLE field_history_log (
    id VARCHAR(64) NOT NULL DEFAULT CONCAT('fHiL_', LEFT(gen_random_uuid()::TEXT, 12)),
    object_name VARCHAR(255) NOT NULL,
    record_id VARCHAR(255) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    user_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    changed_at TIMESTAMPTZ NOT NULL,
    created_date TIMESTAMP DEFAULT now()
);


CREATE TABLE field_tracking_config (
    id VARCHAR(64) NOT NULL DEFAULT CONCAT('fTcoF_', LEFT(gen_random_uuid()::TEXT, 12)),
    object_name VARCHAR(255) NOT NULL,
    field_name VARCHAR(255) NOT NULL,
    is_tracked BOOLEAN NOT NULL,
    created_date TIMESTAMP DEFAULT now(),
    CONSTRAINT field_tracking_config_object_name_field_name_uniq
        UNIQUE (object_name, field_name)
);


CREATE TABLE report_folder_sharing (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('rfsh_', LEFT(gen_random_uuid()::text, 12)),
    
    folder_id VARCHAR(64) NOT NULL,
    shared_with_type VARCHAR(50) NOT NULL,  -- 'user' or 'profile'
    shared_with_id VARCHAR(64) NOT NULL,
    access_level VARCHAR(50) NOT NULL,      -- 'view' or 'manage'

    created_by_id VARCHAR(255),
    created_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    last_modified_by_id VARCHAR(255),
    last_modified_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    organisation VARCHAR(225),
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,

    -- Foreign Keys
    CONSTRAINT fk_rfsh_folder FOREIGN KEY (folder_id) REFERENCES report_folder(id),
    CONSTRAINT fk_rfsh_created_by FOREIGN KEY (created_by_id) REFERENCES public.users(id),
    CONSTRAINT fk_rfsh_last_modified_by FOREIGN KEY (last_modified_by_id) REFERENCES public.users(id)
);



CREATE TABLE IF NOT EXISTS shared_records (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('sRd_', LEFT(gen_random_uuid()::text, 12)),
    object_name TEXT NOT NULL,         -- e.g. 'Account', 'Contact'
    record_id VARCHAR(64) NOT NULL,           -- points to the actual record
    user_id VARCHAR(64) REFERENCES users(id) NOT NULL,     -- the user who gets access
	owner_id VARCHAR(64) REFERENCES users(id) NOT NULL,
    access_mask INT NOT NULL,          -- bitmask: 1=READ, 2=WRITE, 4=DELETE, 8=SHARE
    row_cause TEXT NOT NULL,           -- 'OWNER','OWD','MANUAL','HIERARCHY','RULE','PARENT'
    created_date TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ
);
-- Indexes for lookups
CREATE INDEX idx_record_share_record ON shared_records (object_name, record_id);
CREATE INDEX idx_record_share_user   ON shared_records (user_id);


-- CREATE TABLE IF NOT EXISTS dashboard_assignment(
-- 	id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('dSgn_', LEFT(gen_random_uuid()::text, 12)),
-- 	profile_id VARCHAR(64) REFERENCES profile(id) ON DELETE CASCADE,
-- 	dashboard_id VARCHAR(64) REFERENCES dashboard(id) ON DELETE CASCADE,
-- 	created_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP	
-- );


CREATE TABLE IF NOT EXISTS homepage_assignment(
	id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('cuPas_', LEFT(gen_random_uuid()::text, 12)),
	profile_id VARCHAR(64) REFERENCES profile(id) ON DELETE CASCADE,
	page_id VARCHAR(64) REFERENCES page_builder(id) ON DELETE CASCADE,
	created_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP	
);


CREATE TABLE IF NOT EXISTS notifications(
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('nfy_', LEFT(gen_random_uuid()::text, 12)),
	owner_id VARCHAR(64) REFERENCES users(id) NOT NULL,
    title VARCHAR(255),
    message TEXT NOT NULL,
    channel VARCHAR(20) NOT NULL CHECK (channel IN ('email', 'whatsapp', 'app', 'sms', 'push')),
    type VARCHAR(50) NOT NULL CHECK (type IN ('verification', 'reminder', 'alert', 'system', 'chat')),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'delivered', 'read', 'failed')),
    priority VARCHAR(10) DEFAULT 'normal'CHECK (priority IN ('low', 'normal', 'high')),
    metadata JSONB,   
    url VARCHAR,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    read_at TIMESTAMP NULL,
    sent_at TIMESTAMP NULL,
    delivered_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS telephony_user(
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('TelU_', LEFT(gen_random_uuid()::text, 12)), 
    config_name VARCHAR(50),
    user_id VARCHAR REFERENCES public.users(id) NOT NULL,
    details JSONB,
    status BOOLEAN default TRUE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,   
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS callactivity(
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('CalL_',LEFT(gen_random_uuid()::text,12)),
    data jsonb,
    user_id VARCHAR,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE SEQUENCE task_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE IF NOT EXISTS task (
    id VARCHAR(64) NOT NULL DEFAULT CONCAT('tsK_', LEFT(gen_random_uuid()::TEXT, 14)),
    name VARCHAR(16) DEFAULT 'TASK-' || LPAD(nextval('task_id_seq')::TEXT, 6, '0'),
    subject VARCHAR(512) NOT NULL,
    description TEXT,
    status VARCHAR(255) NOT NULL,
    due_date DATE NOT NULL,
    related_to_object_id VARCHAR(64),
    object_id VARCHAR(64) REFERENCES object(id) ON DELETE CASCADE,
    assigned_to_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    created_by_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    last_modified_by_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    organisation VARCHAR(64),
    is_deleted BOOLEAN DEFAULT FALSE,
    owner_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL
);


CREATE TABLE IF NOT EXISTS email_templates(
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('eTpl_', LEFT(gen_random_uuid()::TEXT, 12)),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    available_for_use BOOLEAN DEFAULT TRUE,
    template_type VARCHAR(10) DEFAULT 'text',
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    author_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    selected_object VARCHAR(255),
    record_id VARCHAR(64),
    sendgrid_template_id VARCHAR(255),
    sendgrid_template_hash VARCHAR(64),
    template_type VARCHAR(50) DEFAULT 'html',
    created_by_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    last_modified_by_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- CREATE TABLE IF NOT EXISTS org_company (
--     id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('oRgN_', LEFT(gen_random_uuid()::text, 12)),
--     company_name VARCHAR(255) NOT NULL,
--     primary_contact VARCHAR(255),
--     division VARCHAR(255),
--     phone VARCHAR(64),
--     fax VARCHAR(64),
--     email VARCHAR(255),
--     website VARCHAR(512),
--     street VARCHAR(512),
--     city VARCHAR(255),
--     state VARCHAR(255),
--     postal_code VARCHAR(32),
--     country VARCHAR(255),
--     default_currency VARCHAR(8) DEFAULT 'USD',
--     default_language VARCHAR(8) DEFAULT 'en',
--     timezone VARCHAR(64) DEFAULT 'UTC',
--     fiscal_year_start_month VARCHAR(16) DEFAULT 'April',
--     description TEXT,
--     logo VARCHAR(2048),
--     created_by_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
--     last_modified_by_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
--     created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
--     last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
--     is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
--     deleted_date TIMESTAMP DEFAULT NULL,
--     deleted_by_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL
-- );