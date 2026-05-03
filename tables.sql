CREATE DOMAIN phone_type AS varchar(20)
CHECK (
    VALUE IS NULL
    OR VALUE ~ '^\+?[1-9][0-9]{7,14}$'
);

CREATE DOMAIN email_type AS varchar(128)
CHECK (
    VALUE IS NULL
    OR VALUE ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
);

CREATE TABLE IF NOT EXISTS accounts (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('aCc_',LEFT(gen_random_uuid()::text, 14)),
    is_deleted BOOLEAN DEFAULT FALSE,
    master_record_id VARCHAR(255) REFERENCES accounts(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(100),
    parent_id VARCHAR(255) REFERENCES accounts(id) ON DELETE SET NULL,
    phone phone_type,
    email email_type,
    fax VARCHAR(50),
    account_number VARCHAR(64),
    account_source VARCHAR(256),
    address_line TEXT,
    contact_number phone_type,
    contact_person_name VARCHAR(255),
    customer_category VARCHAR(100),
    customer_classification VARCHAR(100),
    customer_code VARCHAR(100),
    customer_type VARCHAR(100),
    gst_number VARCHAR(20),
    pan_number VARCHAR(20),
    pincode VARCHAR(20),
    region VARCHAR(100),
    stages VARCHAR(100),
    state VARCHAR(100),
    website VARCHAR(256),
    industry VARCHAR(100),
    annual_revenue NUMERIC(15,2),
    number_of_employees INTEGER,
    description TEXT,
    rating VARCHAR(50),
    site VARCHAR(100),
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_activity_date DATE,
    clean_status VARCHAR(128),
    tradestyle VARCHAR(100),
    year_started VARCHAR(10),
    ownership VARCHAR(100),
    billing_street TEXT,
    billing_home_apartment_no VARCHAR(100),
    billing_city VARCHAR(100),
    billing_state VARCHAR(100),
    billing_postal_code VARCHAR(20),
    billing_country VARCHAR(100),
    shipping_street TEXT,
    shipping_home_apartment_no VARCHAR(100),
    shipping_city VARCHAR(100),
    shipping_state VARCHAR(100),
    shipping_postal_code VARCHAR(20),
    shipping_country VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS contact (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('cntC',LEFT(gen_random_uuid()::text, 12)),
    is_deleted BOOLEAN DEFAULT FALSE,
    master_record_id VARCHAR(255) REFERENCES contact(id) ON DELETE SET NULL,
    account_id VARCHAR(255) REFERENCES accounts(id) ON DELETE SET NULL,
    name VARCHAR(128) NOT NULL,
    level VARCHAR(100),
    salutation VARCHAR(20),
    other_street TEXT,
    other_city VARCHAR(100),
    other_state VARCHAR(100),
    other_postal_code VARCHAR(20),
    other_country VARCHAR(100),
    other_latitude DECIMAL(9,6),
    other_longitude DECIMAL(9,6),
    other_geocode_accuracy VARCHAR(50),
    mailing_street TEXT,
    mailing_city VARCHAR(100),
    mailing_state VARCHAR(100),
    mailing_postal_code VARCHAR(20),
    mailing_country VARCHAR(100),
    mailing_latitude DECIMAL(9,6),
    mailing_longitude DECIMAL(9,6),
    mailing_geocode_accuracy VARCHAR(50),
    phone phone_type,
    contact_number phone_type,
    fax VARCHAR(50),
    contact_source VARCHAR(100),
    home_phone phone_type,
    other_phone phone_type,
    reports_to_id VARCHAR(255) REFERENCES contact(id) ON DELETE SET NULL,
    email email_type,
    title VARCHAR(32),
    department VARCHAR(100),
    assistant_name VARCHAR(128),
    assistant_phone phone_type,
    lead_source VARCHAR(100),
    birthdate DATE,
    description TEXT,
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    has_opted_out_of_email BOOLEAN DEFAULT FALSE,
    has_opted_out_of_fax BOOLEAN DEFAULT FALSE,
    do_not_call BOOLEAN DEFAULT FALSE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    system_modstamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity_date DATE,
    last_cu_request_date TIMESTAMP,
    last_cu_update_date TIMESTAMP,
    email_bounced_reason VARCHAR(255),
    email_bounced_date TIMESTAMP,
    pronouns VARCHAR(50),
    gender_identity VARCHAR(50),
    buyer_attributes TEXT 
);


CREATE TABLE IF NOT EXISTS opportunity (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('OpTnt_',LEFT(gen_random_uuid()::text, 14)),
    is_deleted BOOLEAN DEFAULT FALSE,
    account_id VARCHAR(64) REFERENCES accounts(id) ON DELETE SET NULL,
    name VARCHAR(80) NOT NULL,
    description TEXT,
    ask_for_customer VARCHAR(255),
    amount NUMERIC(15,2),
    probability NUMERIC(5,2),
    number_of_revisions INTEGER,
    discount_percentage NUMERIC(5,2),
    final_approved_value NUMERIC(15,2),
    close_date DATE,
    type VARCHAR(100),
    type_of_sales VARCHAR(100),
    next_step VARCHAR(255),
    lead_source VARCHAR(100),
    project_start_date DATE,
    special_instructions TEXT,
    stages VARCHAR(100),
    last_quote_value NUMERIC(15,2),
    campaign_id VARCHAR(64),
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    contact_id VARCHAR(255) REFERENCES contact(id) ON DELETE SET NULL,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL
);



CREATE TABLE IF NOT EXISTS leads (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('ldS_',LEFT(gen_random_uuid()::text, 14)),
    salutation VARCHAR(20),
    name VARCHAR(64) NOT NULL ,
    master_record_id VARCHAR(255) REFERENCES leads(id) ON DELETE SET NULL,
    stages VARCHAR(100),
    product_enquired VARCHAR(100),
    
    street TEXT,
    region VARCHAR(100),
    area VARCHAR(100),
    pincode VARCHAR(20),
    address_line TEXT,
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    district VARCHAR(100),
    lead_country VARCHAR(100),
    lead_classification VARCHAR(100),
    contact_person_name VARCHAR(255),
    contact_number phone_type,
    industry VARCHAR(100),
    gst_number VARCHAR(20),
    pan VARCHAR(20),
    phone phone_type ,
    mobile_phone phone_type,
    fax VARCHAR(50),
    email email_type,
    website VARCHAR(200),

    description TEXT,
    lead_source VARCHAR(100),
    status VARCHAR(100),
    rating VARCHAR(50),
    annual_revenue NUMERIC(15,2),
    number_of_employees INTEGER,
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    is_converted BOOLEAN DEFAULT FALSE,
    converted_date TIMESTAMP,
    accounts_id VARCHAR(255) REFERENCES accounts(id) ON DELETE SET NULL,
    contact_id VARCHAR(255) REFERENCES contact(id) ON DELETE SET NULL,
    opportunity_id VARCHAR(255) REFERENCES opportunity(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,  
    is_deleted BOOLEAN DEFAULT FALSE,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    company VARCHAR(255),
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL
);


CREATE TABLE IF NOT EXISTS campaign (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('cmP_',LEFT(gen_random_uuid()::text, 12)),
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(255) NOT NULL UNIQUE,
    parent_id VARCHAR(255) REFERENCES campaign(id) ON DELETE SET NULL,
    type VARCHAR(100),
    status VARCHAR(100),
    start_date DATE,
    end_date DATE,
    expected_revenue NUMERIC(15,2),
    budgeted_cost NUMERIC(15,2),
    actual_cost NUMERIC(15,2),
    expected_response VARCHAR(50),
    number_sent INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    description TEXT,
    email_templates_id VARCHAR(64) REFERENCES email_templates(id) ON DELETE SET NULL,
    template VARCHAR(255),
    campaign_image_id VARCHAR(255),
    number_of_leads INTEGER,
    number_of_converted_leads INTEGER,
    number_of_contacts INTEGER,
    number_of_responses INTEGER,
    number_of_opportunities INTEGER,
    number_of_won_opportunities INTEGER,
    amount_all_opportunities NUMERIC(15,2),
    amount_won_opportunities NUMERIC(15,2),
    hierarchy_number_of_leads INTEGER,
    hierarchy_number_of_converted_leads INTEGER,
    hierarchy_number_of_contacts INTEGER,
    hierarchy_number_of_responses INTEGER,
    hierarchy_number_of_opportunities INTEGER,
    hierarchy_number_of_won_opportunities INTEGER,
    hierarchy_amount_all_opportunities NUMERIC(15,2),
    hierarchy_amount_won_opportunities NUMERIC(15,2),
    hierarchy_number_sent INTEGER,
    hierarchy_expected_revenue NUMERIC(15,2),
    hierarchy_budgeted_cost NUMERIC(15,2),
    hierarchy_actual_cost NUMERIC(15,2),
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    system_modstamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity_date DATE,
    campaign_member_record_type_id VARCHAR(255)
);

CREATE SEQUENCE campaign_member_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE campaign_member (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('cmPmB_',LEFT(gen_random_uuid()::text, 12)),
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(50) DEFAULT 'CM-' || LPAD(nextval('campaign_member_id_seq')::TEXT, 9, '0'),
    campaign_id VARCHAR(255) REFERENCES campaign(id) ON DELETE SET NULL,
    lead_id VARCHAR(255) REFERENCES leads(id) ON DELETE SET NULL,
    contact_id VARCHAR(255) REFERENCES contact(id) ON DELETE SET NULL,
    campaign_status VARCHAR(64),
    has_responded BOOLEAN DEFAULT FALSE,
    is_primary BOOLEAN DEFAULT FALSE,
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    system_modstamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    first_responded_date TIMESTAMP
);



CREATE TABLE IF NOT EXISTS product (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('prDut_',LEFT(gen_random_uuid()::text, 12)),
    name VARCHAR(80) NOT NULL UNIQUE,
    product_code VARCHAR(100),
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    family VARCHAR(100),
    external_data_source_id VARCHAR(255),
    external_id VARCHAR(255),
    display_url VARCHAR(255),
    quantity_unit_of_measure NUMERIC(18, 4),
    is_deleted BOOLEAN DEFAULT FALSE,
    is_archived BOOLEAN DEFAULT FALSE,
    stock_keeping_unit VARCHAR(100),
    type VARCHAR(100),
    product_class VARCHAR(100),
    source_product_id VARCHAR(255),
    seller_id VARCHAR(255),
    selling_category VARCHAR(100),
    price NUMERIC(15, 2),
    model VARCHAR(100),
    weight NUMERIC(10,2)
);

CREATE SEQUENCE visit_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE IF NOT EXISTS visit (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('vSt_',LEFT(gen_random_uuid()::text, 12)),
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(10) DEFAULT 'VST-' || LPAD(nextval('visit_id_seq')::TEXT, 6, '0'),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    assigned_to_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    account_id VARCHAR(255) REFERENCES accounts(id) ON DELETE SET NULL,
    contact_id VARCHAR(255) REFERENCES contact(id) ON DELETE SET NULL,
    visit_time TIMESTAMPTZ NOT NULL,
    visit_duration INTEGER,
    type VARCHAR(100),
    notes TEXT,
    status VARCHAR(100)
);

CREATE SEQUENCE invoice_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE IF NOT EXISTS invoice (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('iNvc_',LEFT(gen_random_uuid()::text, 12)),
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(16) DEFAULT 'INV-' || LPAD(nextval('invoice_id_seq')::TEXT, 8, '0'),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    account_id VARCHAR(64) REFERENCES accounts(id) ON DELETE SET NULL,
    email VARCHAR(150),
    aging NUMERIC(10,2),
    balance NUMERIC(15,2),
    batch VARCHAR(255),
    bill_to_contact VARCHAR(255),
    clockout_address TEXT,
    clockout_date TIMESTAMP,
    closed_date TIMESTAMP,
    delivery_status VARCHAR(100),
    due_date DATE,
    invoice_date DATE,
    invoice_outstanding_amount NUMERIC(15,2),
    outstanding_amount NUMERIC(15,2),
    payment_status VARCHAR(100),
    promotional_offer VARCHAR(255),
    status VARCHAR(100),
    store VARCHAR(255),
    vehicle VARCHAR(255),
    work_order VARCHAR(255),
    visit_id VARCHAR(64) REFERENCES visit(id) ON DELETE SET NULL,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE SEQUENCE target_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE IF NOT EXISTS target (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('trGt_',LEFT(gen_random_uuid()::text, 12)),
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(255) DEFAULT 'TRG-' || LPAD(nextval('target_id_seq')::TEXT, 6, '0'),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    system_modstamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    accounts_id VARCHAR(255) REFERENCES accounts(id) ON DELETE SET NULL,
    executive VARCHAR(255),
    incentive NUMERIC(15,2),
    period VARCHAR(100),
    scheme VARCHAR(255),
    team VARCHAR(255),
    actual NUMERIC(15,2),
    target NUMERIC(15,2),
    total_weighted_achievement NUMERIC(15,2),
    variable_pay NUMERIC(15,2),
    basic_pay NUMERIC(15,2),
    total_actual_amount NUMERIC(15,2),
    total_slab_achivement NUMERIC(15,2),
    total_self_target NUMERIC(15,2),
    total_self_actual NUMERIC(15,2),
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE SEQUENCE quote_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE IF NOT EXISTS quote (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('qtE_',LEFT(gen_random_uuid()::text, 12)),
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    deleted_date TIMESTAMP DEFAULT NULL,
    name VARCHAR(32) DEFAULT 'QT-' || LPAD(nextval('quote_id_seq')::TEXT, 6, '0'),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    opportunity_id VARCHAR(255) REFERENCES opportunity(id) ON DELETE SET NULL,
    contact_id VARCHAR(255) REFERENCES contact(id) ON DELETE SET NULL,
    product_id VARCHAR(255) REFERENCES product(id) ON DELETE SET NULL,
    shipping_handling NUMERIC(15,2),
    discount NUMERIC(15,2),
    list_price NUMERIC(15,2),
    quantity NUMERIC(15,2),
    tax NUMERIC(15,2),
    status VARCHAR(100),
    expiration_date DATE,
    description TEXT,
    billing_home_apartment_no VARCHAR(255),
    billing_street TEXT,
    billing_city VARCHAR(100),
    billing_state VARCHAR(100),
    billing_postal_code VARCHAR(20),
    billing_country VARCHAR(100),
    billing_latitude DECIMAL(9,6),
    billing_longitude DECIMAL(9,6),
    billing_geocode_accuracy VARCHAR(50),
    shipping_home_apartment_no VARCHAR(255),
    shipping_street TEXT,
    shipping_city VARCHAR(100),
    shipping_state VARCHAR(100),
    shipping_postal_code VARCHAR(20),
    shipping_country VARCHAR(100),
    shipping_latitude DECIMAL(9,6),
    shipping_longitude DECIMAL(9,6),
    shipping_geocode_accuracy VARCHAR(50),
    quote_to_street TEXT,
    quote_to_city VARCHAR(100),
    quote_to_state VARCHAR(100),
    quote_to_postal_code VARCHAR(20),
    quote_to_country VARCHAR(100),
    quote_to_latitude DECIMAL(9,6),
    quote_to_longitude DECIMAL(9,6),
    quote_to_geocode_accuracy VARCHAR(50),
    additional_street TEXT,
    additional_city VARCHAR(100),
    additional_state VARCHAR(100),
    additional_postal_code VARCHAR(20),
    additional_country VARCHAR(100),
    additional_latitude DECIMAL(9,6),
    additional_longitude DECIMAL(9,6),
    additional_geocode_accuracy VARCHAR(50),
    billing_name VARCHAR(255),
    shipping_name VARCHAR(255),
    quote_to_name VARCHAR(255),
    additional_name VARCHAR(255),
    email VARCHAR(150),
    phone VARCHAR(50),
    fax VARCHAR(50),
    quote_number TEXT,
    is_syncing BOOLEAN DEFAULT FALSE,
    payment_terms VARCHAR(255)
);


CREATE TABLE IF NOT EXISTS opportunity_lineitem (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('oPtlI_',LEFT(gen_random_uuid()::text, 12)),
    name VARCHAR(255),
    opportunity_id VARCHAR(255) REFERENCES opportunity(id) ON DELETE SET NULL,
    sort_order INTEGER,
    pricebook_entry_id VARCHAR(255),
    quantity NUMERIC(15,2),
    discount NUMERIC(15,2),
    unit_price NUMERIC(15,2),
    service_date DATE,
    description TEXT,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    system_modstamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    deleted_date TIMESTAMP,
    quote_line_item_id VARCHAR(255)
);

CREATE SEQUENCE quote_lineitem_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;
CREATE TABLE IF NOT EXISTS quote_line_item (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('qtelI_',LEFT(gen_random_uuid()::text, 12)),
    name VARCHAR(32) DEFAULT 'QTLI-' || LPAD(nextval('quote_lineitem_id_seq')::TEXT, 6, '0'),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    deleted_date TIMESTAMP,
    line_number INTEGER,
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    quote_id VARCHAR(255) REFERENCES quote(id) ON DELETE SET NULL,
    opportunity_lineitem_id VARCHAR(64) REFERENCES opportunity_lineitem(id) ON DELETE SET NULL,
    quantity NUMERIC(15,2),
    unit_price NUMERIC(15,2),
    discount NUMERIC(15,2),
    description TEXT,
    service_date DATE,
    product_id VARCHAR(255) REFERENCES product(id) ON DELETE SET NULL,
    sort_order INTEGER,
    list_price NUMERIC(18,2) DEFAULT 0.00
);

CREATE SEQUENCE invoice_item_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE IF NOT EXISTS invoice_item (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('inVclI_',LEFT(gen_random_uuid()::text, 12)),
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(64) DEFAULT 'INVITEM-' || LPAD(nextval('invoice_item_id_seq')::TEXT, 9, '0'),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    product_id VARCHAR(255) REFERENCES product(id) ON DELETE SET NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    invoice_id VARCHAR(255) REFERENCES invoice(id) ON DELETE SET NULL,
    store_id VARCHAR(64) REFERENCES accounts(id) ON DELETE SET NULL,
    delivery_status VARCHAR(100),
    discount_amount NUMERIC(15,2),
    product VARCHAR(255),
    quantity NUMERIC(15,2),
    size VARCHAR(50),
    store VARCHAR(255),
    tax_percent NUMERIC(5,2),
    unit_price NUMERIC(15,2),
    unit NUMERIC(15,2),
    weight NUMERIC(15,2)
);


CREATE TABLE IF NOT EXISTS target_item (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('tRglI_',LEFT(gen_random_uuid()::text, 12)),
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(255) NOT NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    system_modstamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity_date DATE,
    accounts_id VARCHAR(255) REFERENCES accounts(id) ON DELETE SET NULL,
    actual_value NUMERIC(15,2),
    parent VARCHAR(255),
    soql_query TEXT,
    target_logic VARCHAR(100),
    target_value NUMERIC(15,2),
    target VARCHAR(255),
    teams_actual NUMERIC(15,2),
    teams_target NUMERIC(15,2),
    amount NUMERIC(15,2),
    min_value NUMERIC(15,2),
    max_value NUMERIC(15,2),
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL
);


CREATE TABLE IF NOT EXISTS target_logic (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('tGlgC_',LEFT(gen_random_uuid()::text, 12)),
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(255) NOT NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    system_modstamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity_date DATE,
    account_type VARCHAR(100),
    product_category VARCHAR(100),
    product VARCHAR(255),
    soql_query TEXT,
    selling_category VARCHAR(100),
    target_type VARCHAR(100),
    isactive BOOLEAN DEFAULT TRUE,
    field VARCHAR(255),
    formula TEXT,
    object VARCHAR(100),
    target_plan VARCHAR(255),
    weightage NUMERIC(5,2),
    max_incentive NUMERIC(15,2),
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL
);



CREATE TABLE IF NOT EXISTS product_category (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('pDcaT_',LEFT(gen_random_uuid()::text, 12)),
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(255) NOT NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    system_modstamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    catalog_id VARCHAR(255),
    parent_category_id VARCHAR(255) REFERENCES product_category(id) ON DELETE SET NULL,
    description TEXT,
    sort_order INTEGER,
    is_navigational BOOLEAN DEFAULT FALSE,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE SEQUENCE case_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;


CREATE TABLE IF NOT EXISTS "case" (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('caS_',LEFT(gen_random_uuid()::text, 12)),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    master_record_id VARCHAR(64) REFERENCES "case"(id) ON DELETE SET NULL,
    name VARCHAR(16) DEFAULT 'CASE-' || LPAD(nextval('case_id_seq')::TEXT, 8, '0'),
    email VARCHAR(150),
    contact_id VARCHAR(255) REFERENCES contact(id) ON DELETE SET NULL,
    account_id VARCHAR(255) REFERENCES accounts(id) ON DELETE SET NULL,
    asset_id VARCHAR(255),
    product_id VARCHAR(255),
    source_id VARCHAR(255),
    business_hours_id VARCHAR(255),
    parent_id VARCHAR(255) REFERENCES "case"(id) ON DELETE SET NULL,
    supplied_name VARCHAR(100),
    supplied_email VARCHAR(150),
    supplied_phone VARCHAR(50),
    supplied_company VARCHAR(100),
    status VARCHAR(100),
    reason VARCHAR(100),
    origin VARCHAR(100),
    subject VARCHAR(255),
    priority VARCHAR(50),
    description TEXT,
    is_closed BOOLEAN DEFAULT FALSE,
    closed_date TIMESTAMP,
    is_escalated BOOLEAN DEFAULT FALSE,
    owner_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    is_closed_on_create BOOLEAN DEFAULT FALSE,
    sla_start_date TIMESTAMP,
    sla_exit_date TIMESTAMP,
    is_stopped BOOLEAN DEFAULT FALSE,
    stop_start_date TIMESTAMP,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(255) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    service_contract_id VARCHAR(255),
    events_processed_date TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS file(
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('fLe_', LEFT(gen_random_uuid()::text, 18)),
    name VARCHAR(256) NOT NULL,
    size INTEGER NOT NULL,
    file_path VARCHAR(1024) NOT NULL,
    type VARCHAR(64),
    object VARCHAR(128),
    record_id VARCHAR(64) NOT NULL,   
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    organization_id VARCHAR(64) REFERENCES public.organizations(id) ON DELETE SET NULL, 
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS calendar(
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('cAl_',LEFT(gen_random_uuid()::text, 14)),
    name VARCHAR(255) NOT NULL,
    created_by_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    last_modified_by_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    owner_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    deleted_by_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    object VARCHAR(128),
    subject VARCHAR(256),
    field_for_start VARCHAR(128),
    field_for_end VARCHAR(128),
    filter VARCHAR(128),
    display_field VARCHAR(128)
);

-- Default 'My Events' calendar for event object
-- INSERT INTO calendar (name, object, field_for_start, field_for_end, display_field, filter, created_by_id, owner_id)
-- VALUES ('My Events', 'event', 'start', 'end', 'subject', 'all', 'DYNAMIC_CREATED_BY_ID', 'DYNAMIC_OWNER_ID')
-- ON CONFLICT DO NOTHING;

CREATE SEQUENCE event_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE IF NOT EXISTS event(
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('evNt_', LEFT(gen_random_uuid()::text, 12)), -- Adds 'ND-' as the prefix and limits the UUID to 12 characters
    name VARCHAR(16) DEFAULT 'EVT-' || LPAD(nextval('event_id_seq')::TEXT, 8, '0'),
    location VARCHAR(255),
    description TEXT,
    subject TEXT,
    "start" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "end" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    accounts_id VARCHAR(64) REFERENCES accounts(id) ON DELETE SET NULL,
    leads_id VARCHAR(64) REFERENCES leads(id) ON DELETE SET NULL,
    contacts_id VARCHAR(64) REFERENCES contact(id) ON DELETE SET NULL,
    users_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    deleted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE
);


CREATE SEQUENCE call_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE IF NOT EXISTS call(
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('cAlL_',LEFT(gen_random_uuid()::text,12)),
    name VARCHAR(16) DEFAULT 'CALL-' || LPAD(nextval('call_id_seq')::TEXT, 8, '0'),
    call_type VARCHAR(20) CHECK (call_type IN ('Inbound', 'Outbound')), 
    from_number VARCHAR(20),                       
    to_number VARCHAR(20) NOT NULL, 
    calluuid varchar,
    object_id VARCHAR,                         
    start_time TIMESTAMP NOT NULL,                     
    end_time TIMESTAMP,                                
    duration INT,                
    call_status VARCHAR(20),                                                 
    disposition_value VARCHAR(100),                    
    recording_link TEXT,                              
    call_notes TEXT,                                   
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,   
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL, 
    FOREIGN KEY (object_id) REFERENCES object(id) ON DELETE SET NULL
);

create SEQUENCE email_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE IF NOT EXISTS email(
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('eMl_',LEFT(gen_random_uuid()::text, 12)),
    name VARCHAR(16) DEFAULT 'EML-' || LPAD(nextval('email_id_seq')::TEXT, 8, '0'),
    subject VARCHAR(255),
    body text,
    from_email VARCHAR(150),    
    to_email VARCHAR(150) NOT NULL,
    cc_email VARCHAR(150),
    bcc_email VARCHAR(150),
    sent_time timestamp,
    received_time timestamp,
    email_status VARCHAR(20) CHECK (email_status IN ('Sent', 'Received', 'Draft')),
    attachments text,   
    matched_record_id VARCHAR(60),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    object_id VARCHAR(64) REFERENCES object(id) ON DELETE SET NULL,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (object_id) REFERENCES object(id) ON DELETE SET NULL
);

CREATE SEQUENCE location_track_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE IF NOT EXISTS location_track (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('lOcT_', LEFT(gen_random_uuid()::text, 12)),
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(128) NOT NULL UNIQUE,
    location_id VARCHAR(16) DEFAULT 'LOC-' || LPAD(nextval('location_track_id_seq')::TEXT, 8, '0'),
    check_box BOOLEAN DEFAULT FALSE,
    date DATE,
    "date/time" TIMESTAMP,
    email email_type,
    number NUMERIC(15,2),
    phone phone_type,
    place VARCHAR(255),
    status VARCHAR(100),
    time TIME,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL
);;



CREATE TABLE IF NOT EXISTS activity (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('aCt_', LEFT(gen_random_uuid()::text, 12)),
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(128) NOT NULL UNIQUE,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL
);;

CREATE TABLE IF NOT EXISTS period (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('pEr_', LEFT(gen_random_uuid()::text, 12)),
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(128) NOT NULL UNIQUE,
    start_date DATE,
    end_date DATE,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL
);;

CREATE SEQUENCE target_plan_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE IF NOT EXISTS target_plan (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('tPlN_', LEFT(gen_random_uuid()::text, 12)),
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(16) DEFAULT 'TP-' || LPAD(nextval('target_plan_id_seq')::TEXT, 8, '0'),
    active BOOLEAN DEFAULT TRUE,
    division VARCHAR(255),
    incentive_type VARCHAR(255),
    region VARCHAR(255),
    start_date DATE,
    end_date DATE,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL
);;

CREATE SEQUENCE incentive_slab_id_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1;

CREATE TABLE IF NOT EXISTS incentive_slab (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('iSlB_', LEFT(gen_random_uuid()::text, 12)),
    is_deleted BOOLEAN DEFAULT FALSE,
    name VARCHAR(16) DEFAULT 'IS-' || LPAD(nextval('incentive_slab_id_seq')::TEXT, 8, '0'),
    incentive_amount NUMERIC(15,2),
    incentive_percentage NUMERIC(15,2),
    achievement_from NUMERIC(15,2),
    achievement_to NUMERIC(15,2),
    target_plan_id VARCHAR(64) REFERENCES target_plan(id) ON DELETE SET NULL,
    owner_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    recently_viewed TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    deleted_date TIMESTAMP DEFAULT NULL,
    deleted_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL
);