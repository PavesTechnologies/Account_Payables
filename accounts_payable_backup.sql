--
-- PostgreSQL database dump
--

\restrict v1DXah13nnkz76uPAQztmBznmGgircHZcqaUQ4mpaGlUBkmAh2RTEyb6eANFkUN

-- Dumped from database version 17.10
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: ap; Type: SCHEMA; Schema: -; Owner: avnadmin
--

CREATE SCHEMA ap;


ALTER SCHEMA ap OWNER TO avnadmin;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: audit_log; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.audit_log (
    audit_log_id bigint NOT NULL,
    table_name character varying(50) NOT NULL,
    record_id integer NOT NULL,
    action character varying(20) NOT NULL,
    changed_by character varying(100),
    changed_at timestamp without time zone DEFAULT now() NOT NULL,
    old_values jsonb,
    new_values jsonb
);


ALTER TABLE ap.audit_log OWNER TO avnadmin;

--
-- Name: audit_log_audit_log_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.audit_log_audit_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.audit_log_audit_log_id_seq OWNER TO avnadmin;

--
-- Name: audit_log_audit_log_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.audit_log_audit_log_id_seq OWNED BY ap.audit_log.audit_log_id;


--
-- Name: country; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.country (
    country_id integer NOT NULL,
    country_name character varying(100) NOT NULL,
    country_code character(2) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE ap.country OWNER TO avnadmin;

--
-- Name: country_country_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.country_country_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.country_country_id_seq OWNER TO avnadmin;

--
-- Name: country_country_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.country_country_id_seq OWNED BY ap.country.country_id;


--
-- Name: currency; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.currency (
    currency_id integer NOT NULL,
    currency_name character varying(50) NOT NULL,
    currency_code character(3) NOT NULL,
    symbol character varying(10) NOT NULL,
    decimal_places smallint DEFAULT 2 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE ap.currency OWNER TO avnadmin;

--
-- Name: currency_currency_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.currency_currency_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.currency_currency_id_seq OWNER TO avnadmin;

--
-- Name: currency_currency_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.currency_currency_id_seq OWNED BY ap.currency.currency_id;


--
-- Name: goods_receipt; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.goods_receipt (
    grn_id integer NOT NULL,
    po_id integer,
    vendor_id integer NOT NULL,
    file_path character varying(500),
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    grn_number character varying(50),
    receipt_date date
);


ALTER TABLE ap.goods_receipt OWNER TO avnadmin;

--
-- Name: goods_receipt_grn_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.goods_receipt_grn_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.goods_receipt_grn_id_seq OWNER TO avnadmin;

--
-- Name: goods_receipt_grn_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.goods_receipt_grn_id_seq OWNED BY ap.goods_receipt.grn_id;


--
-- Name: goods_receipt_line; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.goods_receipt_line (
    grn_line_id integer NOT NULL,
    grn_id integer NOT NULL,
    description character varying(255) NOT NULL,
    received_quantity numeric(18,4) NOT NULL,
    po_line_id integer,
    item_code character varying(50)
);


ALTER TABLE ap.goods_receipt_line OWNER TO avnadmin;

--
-- Name: goods_receipt_line_grn_line_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.goods_receipt_line_grn_line_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.goods_receipt_line_grn_line_id_seq OWNER TO avnadmin;

--
-- Name: goods_receipt_line_grn_line_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.goods_receipt_line_grn_line_id_seq OWNED BY ap.goods_receipt_line.grn_line_id;


--
-- Name: inbound_document; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.inbound_document (
    inbound_document_id integer NOT NULL,
    source_type character varying(20) DEFAULT 'EMAIL'::character varying NOT NULL,
    email_from character varying(200),
    email_subject character varying(255),
    email_message_id character varying(255),
    received_at timestamp without time zone DEFAULT now() NOT NULL,
    file_name character varying(255) NOT NULL,
    file_path character varying(500) NOT NULL,
    extraction_status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    extraction_confidence numeric(5,2),
    raw_extracted_data jsonb,
    vendor_id integer,
    invoice_id integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE ap.inbound_document OWNER TO avnadmin;

--
-- Name: inbound_document_inbound_document_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.inbound_document_inbound_document_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.inbound_document_inbound_document_id_seq OWNER TO avnadmin;

--
-- Name: inbound_document_inbound_document_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.inbound_document_inbound_document_id_seq OWNED BY ap.inbound_document.inbound_document_id;


--
-- Name: invoice; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.invoice (
    invoice_id integer NOT NULL,
    invoice_number character varying(50) NOT NULL,
    vendor_id integer NOT NULL,
    inbound_document_id integer,
    invoice_type character varying(20) DEFAULT 'NON_PO'::character varying NOT NULL,
    po_id integer,
    grn_id integer,
    invoice_date date NOT NULL,
    due_date date NOT NULL,
    payment_term_id integer,
    currency_id integer NOT NULL,
    gross_amount numeric(18,2) NOT NULL,
    discount_amount numeric(18,2) DEFAULT 0 NOT NULL,
    tax_amount numeric(18,2) DEFAULT 0 NOT NULL,
    net_amount numeric(18,2) NOT NULL,
    amount_paid numeric(18,2) DEFAULT 0 NOT NULL,
    status_id integer,
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_by character varying(100),
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE ap.invoice OWNER TO avnadmin;

--
-- Name: invoice_approval; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.invoice_approval (
    invoice_approval_id integer NOT NULL,
    invoice_id integer NOT NULL,
    invoice_issue_id integer,
    approver_name character varying(150) NOT NULL,
    decision character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    comments character varying(500),
    decided_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE ap.invoice_approval OWNER TO avnadmin;

--
-- Name: invoice_approval_invoice_approval_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.invoice_approval_invoice_approval_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.invoice_approval_invoice_approval_id_seq OWNER TO avnadmin;

--
-- Name: invoice_approval_invoice_approval_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.invoice_approval_invoice_approval_id_seq OWNED BY ap.invoice_approval.invoice_approval_id;


--
-- Name: invoice_attachment; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.invoice_attachment (
    invoice_attachment_id integer NOT NULL,
    invoice_id integer NOT NULL,
    file_name character varying(255) NOT NULL,
    file_path character varying(500) NOT NULL,
    uploaded_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE ap.invoice_attachment OWNER TO avnadmin;

--
-- Name: invoice_attachment_invoice_attachment_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.invoice_attachment_invoice_attachment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.invoice_attachment_invoice_attachment_id_seq OWNER TO avnadmin;

--
-- Name: invoice_attachment_invoice_attachment_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.invoice_attachment_invoice_attachment_id_seq OWNED BY ap.invoice_attachment.invoice_attachment_id;


--
-- Name: invoice_invoice_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.invoice_invoice_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.invoice_invoice_id_seq OWNER TO avnadmin;

--
-- Name: invoice_invoice_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.invoice_invoice_id_seq OWNED BY ap.invoice.invoice_id;


--
-- Name: invoice_issue; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.invoice_issue (
    invoice_issue_id integer NOT NULL,
    invoice_id integer NOT NULL,
    issue_source character varying(20) NOT NULL,
    issue_type character varying(50) NOT NULL,
    severity character varying(10) DEFAULT 'ERROR'::character varying NOT NULL,
    result character varying(10),
    description character varying(255),
    status_id integer,
    resolved_by character varying(100),
    resolved_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT invoice_issue_severity_check CHECK (((severity)::text = ANY (ARRAY[('INFO'::character varying)::text, ('WARNING'::character varying)::text, ('ERROR'::character varying)::text])))
);


ALTER TABLE ap.invoice_issue OWNER TO avnadmin;

--
-- Name: invoice_issue_invoice_issue_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.invoice_issue_invoice_issue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.invoice_issue_invoice_issue_id_seq OWNER TO avnadmin;

--
-- Name: invoice_issue_invoice_issue_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.invoice_issue_invoice_issue_id_seq OWNED BY ap.invoice_issue.invoice_issue_id;


--
-- Name: invoice_line; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.invoice_line (
    invoice_line_id integer NOT NULL,
    invoice_id integer NOT NULL,
    line_number smallint NOT NULL,
    description character varying(255) NOT NULL,
    quantity numeric(18,4) DEFAULT 1 NOT NULL,
    unit_price numeric(18,4) NOT NULL,
    line_amount numeric(18,2) NOT NULL,
    tax_type_id integer,
    tax_amount numeric(18,2) DEFAULT 0 NOT NULL
);


ALTER TABLE ap.invoice_line OWNER TO avnadmin;

--
-- Name: invoice_line_invoice_line_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.invoice_line_invoice_line_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.invoice_line_invoice_line_id_seq OWNER TO avnadmin;

--
-- Name: invoice_line_invoice_line_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.invoice_line_invoice_line_id_seq OWNED BY ap.invoice_line.invoice_line_id;


--
-- Name: payment; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.payment (
    payment_id integer NOT NULL,
    vendor_id integer NOT NULL,
    vendor_bank_id integer,
    scheduled_date date NOT NULL,
    payment_date date,
    total_amount numeric(18,2) NOT NULL,
    currency_id integer NOT NULL,
    payment_method character varying(30) NOT NULL,
    reference_number character varying(100),
    status_id integer,
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_by character varying(100),
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE ap.payment OWNER TO avnadmin;

--
-- Name: payment_invoice; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.payment_invoice (
    payment_invoice_id integer NOT NULL,
    payment_id integer NOT NULL,
    invoice_id integer NOT NULL,
    allocated_amount numeric(18,2) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE ap.payment_invoice OWNER TO avnadmin;

--
-- Name: payment_invoice_payment_invoice_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.payment_invoice_payment_invoice_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.payment_invoice_payment_invoice_id_seq OWNER TO avnadmin;

--
-- Name: payment_invoice_payment_invoice_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.payment_invoice_payment_invoice_id_seq OWNED BY ap.payment_invoice.payment_invoice_id;


--
-- Name: payment_payment_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.payment_payment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.payment_payment_id_seq OWNER TO avnadmin;

--
-- Name: payment_payment_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.payment_payment_id_seq OWNED BY ap.payment.payment_id;


--
-- Name: payment_term; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.payment_term (
    payment_term_id integer NOT NULL,
    term_name character varying(50) NOT NULL,
    due_days smallint DEFAULT 0 NOT NULL,
    discount_percent numeric(5,2) DEFAULT 0 NOT NULL,
    discount_days smallint DEFAULT 0 NOT NULL,
    is_system_default boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_by character varying(100),
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE ap.payment_term OWNER TO avnadmin;

--
-- Name: payment_term_payment_term_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.payment_term_payment_term_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.payment_term_payment_term_id_seq OWNER TO avnadmin;

--
-- Name: payment_term_payment_term_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.payment_term_payment_term_id_seq OWNED BY ap.payment_term.payment_term_id;


--
-- Name: purchase_order; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.purchase_order (
    po_id integer NOT NULL,
    po_number character varying(50) NOT NULL,
    vendor_id integer NOT NULL,
    file_path character varying(500),
    status_id integer,
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    po_date date,
    expected_delivery_date date,
    currency_id integer,
    subtotal numeric(18,2),
    tax_amount numeric(18,2),
    total_amount numeric(18,2)
);


ALTER TABLE ap.purchase_order OWNER TO avnadmin;

--
-- Name: purchase_order_line; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.purchase_order_line (
    po_line_id integer NOT NULL,
    po_id integer NOT NULL,
    description character varying(255) NOT NULL,
    quantity numeric(18,4) DEFAULT 1 NOT NULL,
    unit_price numeric(18,4) NOT NULL,
    tax_amount numeric(18,2) DEFAULT 0 NOT NULL,
    line_amount numeric(18,2) NOT NULL,
    item_code character varying(50)
);


ALTER TABLE ap.purchase_order_line OWNER TO avnadmin;

--
-- Name: purchase_order_line_po_line_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.purchase_order_line_po_line_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.purchase_order_line_po_line_id_seq OWNER TO avnadmin;

--
-- Name: purchase_order_line_po_line_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.purchase_order_line_po_line_id_seq OWNED BY ap.purchase_order_line.po_line_id;


--
-- Name: purchase_order_po_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.purchase_order_po_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.purchase_order_po_id_seq OWNER TO avnadmin;

--
-- Name: purchase_order_po_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.purchase_order_po_id_seq OWNED BY ap.purchase_order.po_id;


--
-- Name: status_master; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.status_master (
    status_id integer NOT NULL,
    module_name character varying(50) NOT NULL,
    status_code character varying(30) NOT NULL,
    status_name character varying(100) NOT NULL,
    display_order smallint DEFAULT 0 NOT NULL
);


ALTER TABLE ap.status_master OWNER TO avnadmin;

--
-- Name: status_master_status_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.status_master_status_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.status_master_status_id_seq OWNER TO avnadmin;

--
-- Name: status_master_status_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.status_master_status_id_seq OWNED BY ap.status_master.status_id;


--
-- Name: system_configuration; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.system_configuration (
    config_key character varying(100) NOT NULL,
    config_value character varying(255) NOT NULL,
    data_type character varying(20) DEFAULT 'STRING'::character varying NOT NULL,
    description character varying(255),
    updated_by character varying(100),
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE ap.system_configuration OWNER TO avnadmin;

--
-- Name: tax_type; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.tax_type (
    tax_type_id integer NOT NULL,
    country_id integer NOT NULL,
    tax_name character varying(100) NOT NULL,
    tax_code character varying(30) NOT NULL,
    calculation_type character varying(20) DEFAULT 'PERCENTAGE'::character varying NOT NULL,
    rate_percent numeric(6,3),
    fixed_amount numeric(18,2),
    is_withholding boolean DEFAULT false NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    is_system_default boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_by character varying(100),
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT tax_type_check CHECK (((((calculation_type)::text = 'PERCENTAGE'::text) AND (rate_percent IS NOT NULL)) OR (((calculation_type)::text = 'FIXED'::text) AND (fixed_amount IS NOT NULL))))
);


ALTER TABLE ap.tax_type OWNER TO avnadmin;

--
-- Name: tax_type_tax_type_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.tax_type_tax_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.tax_type_tax_type_id_seq OWNER TO avnadmin;

--
-- Name: tax_type_tax_type_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.tax_type_tax_type_id_seq OWNED BY ap.tax_type.tax_type_id;


--
-- Name: vendor; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.vendor (
    vendor_id integer NOT NULL,
    vendor_name character varying(200) NOT NULL,
    vendor_code character varying(30),
    country_id integer NOT NULL,
    payment_term_id integer,
    currency_id integer,
    phone_number character varying(30),
    email character varying(150),
    status_id integer,
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_by character varying(100),
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    pan_number character varying(10)
);


ALTER TABLE ap.vendor OWNER TO avnadmin;

--
-- Name: vendor_address; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.vendor_address (
    vendor_address_id integer NOT NULL,
    vendor_id integer NOT NULL,
    address_type character varying(30) DEFAULT 'REGISTERED'::character varying NOT NULL,
    address_line1 character varying(200) NOT NULL,
    address_line2 character varying(200),
    city character varying(100) NOT NULL,
    state character varying(100),
    postal_code character varying(20),
    country_id integer NOT NULL,
    is_primary boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE ap.vendor_address OWNER TO avnadmin;

--
-- Name: vendor_address_vendor_address_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.vendor_address_vendor_address_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.vendor_address_vendor_address_id_seq OWNER TO avnadmin;

--
-- Name: vendor_address_vendor_address_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.vendor_address_vendor_address_id_seq OWNED BY ap.vendor_address.vendor_address_id;


--
-- Name: vendor_bank; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.vendor_bank (
    vendor_bank_id integer NOT NULL,
    vendor_id integer NOT NULL,
    bank_name character varying(150) NOT NULL,
    account_holder_name character varying(150) NOT NULL,
    account_number character varying(50),
    iban character varying(50),
    swift_code character varying(20),
    routing_number character varying(20),
    ifsc_code character varying(20),
    is_primary boolean DEFAULT false NOT NULL,
    effective_from date DEFAULT CURRENT_DATE NOT NULL,
    effective_to date,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE ap.vendor_bank OWNER TO avnadmin;

--
-- Name: vendor_bank_vendor_bank_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.vendor_bank_vendor_bank_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.vendor_bank_vendor_bank_id_seq OWNER TO avnadmin;

--
-- Name: vendor_bank_vendor_bank_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.vendor_bank_vendor_bank_id_seq OWNED BY ap.vendor_bank.vendor_bank_id;


--
-- Name: vendor_tax; Type: TABLE; Schema: ap; Owner: avnadmin
--

CREATE TABLE ap.vendor_tax (
    vendor_tax_id integer NOT NULL,
    registration_type character varying(30) NOT NULL,
    registration_number character varying(50) NOT NULL,
    is_verified boolean DEFAULT false NOT NULL,
    verified_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    vendor_address_id integer
);


ALTER TABLE ap.vendor_tax OWNER TO avnadmin;

--
-- Name: vendor_tax_vendor_tax_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.vendor_tax_vendor_tax_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.vendor_tax_vendor_tax_id_seq OWNER TO avnadmin;

--
-- Name: vendor_tax_vendor_tax_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.vendor_tax_vendor_tax_id_seq OWNED BY ap.vendor_tax.vendor_tax_id;


--
-- Name: vendor_vendor_id_seq; Type: SEQUENCE; Schema: ap; Owner: avnadmin
--

CREATE SEQUENCE ap.vendor_vendor_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ap.vendor_vendor_id_seq OWNER TO avnadmin;

--
-- Name: vendor_vendor_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: avnadmin
--

ALTER SEQUENCE ap.vendor_vendor_id_seq OWNED BY ap.vendor.vendor_id;


--
-- Name: audit_log audit_log_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.audit_log ALTER COLUMN audit_log_id SET DEFAULT nextval('ap.audit_log_audit_log_id_seq'::regclass);


--
-- Name: country country_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.country ALTER COLUMN country_id SET DEFAULT nextval('ap.country_country_id_seq'::regclass);


--
-- Name: currency currency_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.currency ALTER COLUMN currency_id SET DEFAULT nextval('ap.currency_currency_id_seq'::regclass);


--
-- Name: goods_receipt grn_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.goods_receipt ALTER COLUMN grn_id SET DEFAULT nextval('ap.goods_receipt_grn_id_seq'::regclass);


--
-- Name: goods_receipt_line grn_line_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.goods_receipt_line ALTER COLUMN grn_line_id SET DEFAULT nextval('ap.goods_receipt_line_grn_line_id_seq'::regclass);


--
-- Name: inbound_document inbound_document_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.inbound_document ALTER COLUMN inbound_document_id SET DEFAULT nextval('ap.inbound_document_inbound_document_id_seq'::regclass);


--
-- Name: invoice invoice_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice ALTER COLUMN invoice_id SET DEFAULT nextval('ap.invoice_invoice_id_seq'::regclass);


--
-- Name: invoice_approval invoice_approval_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_approval ALTER COLUMN invoice_approval_id SET DEFAULT nextval('ap.invoice_approval_invoice_approval_id_seq'::regclass);


--
-- Name: invoice_attachment invoice_attachment_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_attachment ALTER COLUMN invoice_attachment_id SET DEFAULT nextval('ap.invoice_attachment_invoice_attachment_id_seq'::regclass);


--
-- Name: invoice_issue invoice_issue_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_issue ALTER COLUMN invoice_issue_id SET DEFAULT nextval('ap.invoice_issue_invoice_issue_id_seq'::regclass);


--
-- Name: invoice_line invoice_line_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_line ALTER COLUMN invoice_line_id SET DEFAULT nextval('ap.invoice_line_invoice_line_id_seq'::regclass);


--
-- Name: payment payment_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment ALTER COLUMN payment_id SET DEFAULT nextval('ap.payment_payment_id_seq'::regclass);


--
-- Name: payment_invoice payment_invoice_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment_invoice ALTER COLUMN payment_invoice_id SET DEFAULT nextval('ap.payment_invoice_payment_invoice_id_seq'::regclass);


--
-- Name: payment_term payment_term_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment_term ALTER COLUMN payment_term_id SET DEFAULT nextval('ap.payment_term_payment_term_id_seq'::regclass);


--
-- Name: purchase_order po_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.purchase_order ALTER COLUMN po_id SET DEFAULT nextval('ap.purchase_order_po_id_seq'::regclass);


--
-- Name: purchase_order_line po_line_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.purchase_order_line ALTER COLUMN po_line_id SET DEFAULT nextval('ap.purchase_order_line_po_line_id_seq'::regclass);


--
-- Name: status_master status_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.status_master ALTER COLUMN status_id SET DEFAULT nextval('ap.status_master_status_id_seq'::regclass);


--
-- Name: tax_type tax_type_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.tax_type ALTER COLUMN tax_type_id SET DEFAULT nextval('ap.tax_type_tax_type_id_seq'::regclass);


--
-- Name: vendor vendor_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor ALTER COLUMN vendor_id SET DEFAULT nextval('ap.vendor_vendor_id_seq'::regclass);


--
-- Name: vendor_address vendor_address_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor_address ALTER COLUMN vendor_address_id SET DEFAULT nextval('ap.vendor_address_vendor_address_id_seq'::regclass);


--
-- Name: vendor_bank vendor_bank_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor_bank ALTER COLUMN vendor_bank_id SET DEFAULT nextval('ap.vendor_bank_vendor_bank_id_seq'::regclass);


--
-- Name: vendor_tax vendor_tax_id; Type: DEFAULT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor_tax ALTER COLUMN vendor_tax_id SET DEFAULT nextval('ap.vendor_tax_vendor_tax_id_seq'::regclass);


--
-- Data for Name: audit_log; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.audit_log (audit_log_id, table_name, record_id, action, changed_by, changed_at, old_values, new_values) FROM stdin;
1	vendor	1	CREATE	1	2026-07-24 10:21:14.925762	null	{"email": "ap@infosys.com", "status_id": 1, "country_id": 1, "pan_number": "AAACI1681G", "currency_id": 1, "vendor_code": "VND001", "vendor_name": "Infosys Limited", "phone_number": "9876543210", "payment_term_id": 1}
2	vendor	1	STATUS_CHANGE	1	2026-07-24 10:22:01.151424	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
3	vendor	2	CREATE	1	2026-07-24 10:22:55.32128	null	{"email": "finance@tcs.com", "status_id": 1, "country_id": 1, "pan_number": "AAACT4364B", "currency_id": 1, "vendor_code": "VND002", "vendor_name": "TCS Limited", "phone_number": "9123456789", "payment_term_id": 2}
4	vendor	3	CREATE	1	2026-07-24 10:23:29.333754	null	{"email": "vendor@microsoft.com", "status_id": 1, "country_id": 3, "pan_number": null, "currency_id": 2, "vendor_code": "VND003", "vendor_name": "Microsoft Corporation", "phone_number": "+12065551234", "payment_term_id": 1}
5	vendor	4	CREATE	1	2026-07-24 10:30:13.562413	null	{"email": "vendor@microsoft.com", "status_id": 1, "country_id": 3, "pan_number": null, "currency_id": 2, "vendor_code": "VND0003", "vendor_name": "Microsoft Corporationn", "phone_number": "+12065551234", "payment_term_id": 1}
6	vendor	5	CREATE	1	2026-07-27 07:37:22.386225	null	{"email": "accounts@abctech.com", "status_id": 1, "country_id": 1, "pan_number": "ABCDE1234F", "currency_id": 1, "vendor_code": "VND001", "vendor_name": "ABC Technologies Pvt Ltd", "phone_number": "+919876543210", "payment_term_id": 1}
7	vendor	6	CREATE	1	2026-07-27 07:37:42.255114	null	{"email": "billing@xyzproperties.com", "status_id": 1, "country_id": 1, "pan_number": "AAACP1234K", "currency_id": 1, "vendor_code": "VND002", "vendor_name": "XYZ Properties Pvt Ltd", "phone_number": "+919812345678", "payment_term_id": 2}
8	vendor	7	CREATE	1	2026-07-27 07:37:59.494497	null	{"email": "finance@fasttrack.com", "status_id": 1, "country_id": 1, "pan_number": "AACCF5678L", "currency_id": 1, "vendor_code": "VND003", "vendor_name": "FastTrack Logistics Pvt Ltd", "phone_number": "+919900112233", "payment_term_id": 3}
9	vendor_address	6	CREATE	1	2026-07-27 09:08:39.279343	null	{"city": "Hyderabad", "state": "Telangana", "country_id": 1, "is_primary": true, "postal_code": "500081", "address_type": "REGISTERED", "address_line1": "Plot No. 45, HITEC City", "address_line2": "Madhapur"}
10	vendor_bank	5	CREATE	1	2026-07-27 09:36:07.134496	null	{"iban": "", "bank_name": "HDFC Bank", "ifsc_code": "HDFC0001234", "is_primary": true, "swift_code": "HDFCINBB", "account_number": "1234567890123456", "routing_number": "", "account_holder_name": "FastTrack Logistics Pvt Ltd"}
11	vendor_bank	6	CREATE	1	2026-07-27 09:36:18.34275	null	{"iban": "", "bank_name": "HDFC Bank", "ifsc_code": "HDFC0001234", "is_primary": true, "swift_code": "HDFCINBB", "account_number": "1234567890123456", "routing_number": "", "account_holder_name": "FastTrack Logistics Pvt Ltd"}
12	vendor_tax	5	CREATE	1	2026-07-27 10:09:10.623285	null	{"is_verified": false, "registration_type": "GST", "registration_number": "29ABCDE1234F1Z5"}
13	vendor	8	CREATE	1	2026-07-27 10:13:00.347465	null	{"email": "accounts@abctech.com", "status_id": 1, "country_id": 1, "pan_number": null, "currency_id": 1, "vendor_code": "VND005", "vendor_name": "xyz Technologies Pvt Ltd", "phone_number": "+919876543210", "payment_term_id": 1}
14	vendor	8	UPDATE	1	2026-07-27 10:14:18.453458	{"email": "accounts@abctech.com", "vendor_name": "xyz Technologies Pvt Ltd", "phone_number": "+919876543210", "payment_term_id": 1}	{"email": "finance@abctech.com", "vendor_name": "RRS Technologies Private Limited", "phone_number": "+919812345678", "payment_term_id": 2}
15	vendor_address	7	CREATE	1	2026-07-27 10:15:01.069335	null	{"city": "Bengaluru", "state": "Karnataka", "country_id": 1, "is_primary": true, "postal_code": "560001", "address_type": "Registered", "address_line1": "No. 12, MG Road", "address_line2": "Near Metro Station"}
16	vendor_address	7	UPDATE	1	2026-07-27 10:15:35.343361	{"postal_code": "560001"}	{"postal_code": "560004"}
17	vendor_bank	7	CREATE	1	2026-07-27 10:16:19.654303	null	{"iban": "", "bank_name": "HDFC Bank", "ifsc_code": "HDFC0001234", "is_primary": true, "swift_code": "HDFCINBB", "account_number": "1234567890123456", "routing_number": "", "account_holder_name": "ABC Technologies Pvt Ltd"}
18	vendor_bank	7	UPDATE	1	2026-07-27 10:16:51.844861	{"swift_code": "HDFCINBB"}	{"swift_code": "HDFCINBBB"}
19	vendor_tax	6	CREATE	1	2026-07-27 10:17:47.37958	null	{"is_verified": false, "registration_type": "GST", "registration_number": "29ABCDE1234F1Z5"}
20	vendor_tax	6	UPDATE	1	2026-07-27 10:18:49.930676	{"registration_type": "GST"}	{"registration_type": "TAN"}
21	vendor	9	CREATE	1	2026-07-28 09:43:10.954211	null	{"email": "galiv0758@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAPCP4212K", "currency_id": 1, "vendor_code": null, "vendor_name": "PAVES GLOBAL INFOTECH PRIVATE LIMITED", "phone_number": "8270661122", "payment_term_id": 1}
22	vendor	9	STATUS_CHANGE	1	2026-07-28 09:50:46.559192	{"status_id": 1}	{"status_id": 3, "status_code": "INACTIVE"}
23	vendor	10	CREATE	1	2026-07-28 10:09:48.486249	null	{"email": "galiv0758@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAPCP4212K", "currency_id": 2, "vendor_code": null, "vendor_name": "PAVES GLOBAL INFOTECH PRIVATE LIMITED", "phone_number": "8270661122", "payment_term_id": 1}
24	vendor	11	CREATE	1	2026-07-28 10:20:56.457985	null	{"email": "galiv0758@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAPCP4212K", "currency_id": 2, "vendor_code": null, "vendor_name": "PAVES GLOBAL INFOTECH PRIVATE LIMITED", "phone_number": "8270661122", "payment_term_id": 1}
25	vendor_address	8	CREATE	1	2026-07-28 10:20:57.329481	null	{"city": "Hyderabad", "state": "Telangana", "country_id": 1, "is_primary": true, "postal_code": "500037", "address_type": "REGISTERED", "address_line1": "PLOT NO.121/MIG-II GANDHI NAGAR CHINTHAL", "address_line2": "APHB Colony, Rangareddy"}
26	vendor_tax	7	CREATE	1	2026-07-28 10:20:58.014495	null	{"is_verified": false, "registration_type": "GST", "registration_number": "36AAPCP4212K1Z6"}
27	vendor	11	STATUS_CHANGE	1	2026-07-28 10:24:12.758668	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
28	vendor	12	CREATE	1	2026-07-28 10:56:44.5184	null	{"email": "galiv0758@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAPCP4212K", "currency_id": 1, "vendor_code": "PGIPL2644", "vendor_name": "PAVES GLOBAL INFOTECH PRIVATE LIMITED", "phone_number": "8270661122", "payment_term_id": 1}
29	vendor_address	9	CREATE	1	2026-07-28 10:56:45.295107	null	{"city": "Hyderabad", "state": "Telangana", "country_id": 1, "is_primary": true, "postal_code": "500037", "address_type": "REGISTERED", "address_line1": "PLOT NO.121/MIG-II GANDHI NAGAR CHINTHAL", "address_line2": "APHB Colony, Rangareddy"}
30	vendor_tax	8	CREATE	1	2026-07-28 10:56:46.083095	null	{"is_verified": true, "registration_type": "GST", "registration_number": "36AAPCP4212K1Z6"}
31	vendor	12	STATUS_CHANGE	1	2026-07-28 10:57:07.523396	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
32	vendor	13	CREATE	1	2026-07-28 11:54:20.223761	null	{"email": "galivv0758@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAPCP4212K", "currency_id": 1, "vendor_code": "PGIPL2420", "vendor_name": "PAVES GLOBAL INFOTECH PRIVATE LIMITED", "phone_number": "8270661122", "payment_term_id": null}
33	vendor_address	10	CREATE	1	2026-07-28 11:54:21.135644	null	{"city": "Hyderabad", "state": "Telangana", "country_id": 1, "is_primary": true, "postal_code": "500037", "address_type": "REGISTERED", "address_line1": "PLOT NO.121/MIG-II GANDHI NAGAR CHINTHAL", "address_line2": "APHB Colony, Rangareddy"}
34	vendor_tax	9	CREATE	1	2026-07-28 11:54:21.76405	null	{"is_verified": true, "registration_type": "GST", "registration_number": "36AAPCP4212K1Z6"}
35	vendor	13	STATUS_CHANGE	1	2026-07-28 11:54:54.703666	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
36	vendor	14	CREATE	1	2026-07-29 06:57:34.725414	null	{"email": "galiioo0758@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAPCP2129K", "currency_id": 1, "vendor_code": "ijijii2736", "vendor_name": "ieiji jj ijw joj iji@jj ij", "phone_number": "090008090090", "payment_term_id": 1}
37	vendor	7	STATUS_CHANGE	1	2026-08-07 12:25:04.026683	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
38	vendor	7	STATUS_CHANGE	1	2026-08-07 12:26:30.068804	{"status_id": 2}	{"status_id": 3, "status_code": "INACTIVE"}
39	vendor	15	CREATE	5100031	2026-08-10 16:33:37.113797	null	{"email": "support.aws@example.com", "status_id": 1, "country_id": 1, "pan_number": "AAJCA9880A", "currency_id": 1, "vendor_code": "AWSIPL0336", "vendor_name": "AMAZON WEB SERVICES INDIA PRIVATE LIMITED", "phone_number": "9100633230", "payment_term_id": 2}
40	vendor_address	11	CREATE	5100031	2026-08-10 16:33:37.822493	null	{"city": "NEHRU PLACE", "state": "Delhi", "country_id": 1, "is_primary": true, "postal_code": "110019", "address_type": "REGISTERED", "address_line1": "Block E", "address_line2": "International Trade Tower, South Delhi"}
41	vendor_tax	10	CREATE	5100031	2026-08-10 16:33:38.28736	null	{"is_verified": true, "registration_type": "GST", "registration_number": "07AAJCA9880A1ZL"}
42	vendor	15	STATUS_CHANGE	5100031	2026-08-10 16:33:44.135912	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
43	vendor	16	CREATE	5100031	2026-08-11 13:40:20.883477	null	{"email": "admin.keka@keka.com", "status_id": 1, "country_id": 1, "pan_number": "AAFCK5835K", "currency_id": 1, "vendor_code": "KTPL1020", "vendor_name": "KEKA TECHNOLOGIES PRIVATE LIMITED", "phone_number": "9122541230", "payment_term_id": null}
44	vendor_address	12	CREATE	5100031	2026-08-11 13:40:21.482888	null	{"city": "Hyderabad", "state": "Telangana", "country_id": 1, "is_primary": true, "postal_code": "500032", "address_type": "REGISTERED", "address_line1": "Survey no. 17 Vasavi Shalom Sky City", "address_line2": "Gachibowli, Rangareddy"}
45	vendor_tax	11	CREATE	5100031	2026-08-11 13:40:21.934612	null	{"is_verified": true, "registration_type": "GST", "registration_number": "36AAFCK5835K1Z6"}
46	vendor	16	STATUS_CHANGE	5100031	2026-08-11 13:40:26.16395	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
47	purchase_order	1	CREATE	1	2026-08-12 07:36:44.227842	null	{"file_path": null, "po_number": "PO-TEST-001", "status_id": 14, "vendor_id": 16}
48	goods_receipt	1	CREATE	1	2026-08-12 09:17:12.087555	null	{"po_id": 1, "file_path": null, "vendor_id": 16}
49	purchase_order	1	UPDATE	1	2026-08-12 09:40:49.393024	{"file_path": null}	{"file_path": "invoices/2026/08/54728085edd449f581175e70f10c5291_invoice_1.pdf"}
50	purchase_order	2	CREATE	test-script	2026-08-12 11:27:42.097628	null	{"po_date": "2026-08-01", "subtotal": "1000.00", "file_path": null, "po_number": "TEST-PO-0001", "status_id": 14, "vendor_id": 15, "tax_amount": "180.00", "currency_id": 1, "total_amount": "1180.00", "expected_delivery_date": "2026-08-15"}
51	purchase_order	2	UPDATE	test-script	2026-08-12 11:27:42.523937	{"subtotal": "1000.00"}	{"subtotal": "500.00"}
52	goods_receipt	2	CREATE	test-script	2026-08-12 11:27:43.492807	null	{"po_id": null, "file_path": null, "vendor_id": 15, "grn_number": "TEST-GRN-0001", "receipt_date": "2026-08-05"}
53	goods_receipt	3	CREATE	test-script	2026-08-12 11:27:43.824721	null	{"po_id": 2, "file_path": null, "vendor_id": 15, "grn_number": "TEST-GRN-0002", "receipt_date": "2026-08-06"}
54	goods_receipt	2	UPDATE	test-script	2026-08-12 11:27:44.281475	{"grn_number": "TEST-GRN-0001"}	{"grn_number": "TEST-GRN-0001-REV"}
57	goods_receipt	3	DELETE	cleanup	2026-08-12 11:31:19.197417	{"po_id": 2, "file_path": null, "vendor_id": 15, "grn_number": "TEST-GRN-0002", "receipt_date": "2026-08-06"}	null
58	goods_receipt	2	DELETE	cleanup	2026-08-12 11:31:19.567634	{"po_id": null, "file_path": null, "vendor_id": 15, "grn_number": "TEST-GRN-0001-REV", "receipt_date": "2026-08-05"}	null
59	purchase_order	2	DELETE	cleanup	2026-08-12 11:31:19.902778	{"po_date": "2026-08-01", "subtotal": "500.00", "file_path": null, "po_number": "TEST-PO-0001", "status_id": 14, "vendor_id": 15, "tax_amount": "180.00", "currency_id": 1, "total_amount": "1180.00", "expected_delivery_date": "2026-08-15"}	null
60	purchase_order	3	CREATE	test-script	2026-08-12 11:31:43.449692	null	{"po_date": "2026-08-01", "subtotal": "1000.00", "file_path": null, "po_number": "TEST-PO-0001", "status_id": 14, "vendor_id": 15, "tax_amount": "180.00", "currency_id": 1, "total_amount": "1180.00", "expected_delivery_date": "2026-08-15"}
61	purchase_order	3	UPDATE	test-script	2026-08-12 11:31:44.005436	{"subtotal": "1000.00"}	{"subtotal": "500.00"}
62	goods_receipt	5	CREATE	test-script	2026-08-12 11:31:44.776613	null	{"po_id": null, "file_path": null, "vendor_id": 15, "grn_number": "TEST-GRN-0001", "receipt_date": "2026-08-05"}
63	goods_receipt	6	CREATE	test-script	2026-08-12 11:31:45.186202	null	{"po_id": 3, "file_path": null, "vendor_id": 15, "grn_number": "TEST-GRN-0002", "receipt_date": "2026-08-06"}
64	goods_receipt	5	UPDATE	test-script	2026-08-12 11:31:45.6435	{"grn_number": "TEST-GRN-0001"}	{"grn_number": "TEST-GRN-0001-REV"}
65	goods_receipt	5	DELETE	test-script	2026-08-12 11:31:46.391666	{"po_id": null, "file_path": null, "vendor_id": 15, "grn_number": "TEST-GRN-0001-REV", "receipt_date": "2026-08-05"}	null
66	goods_receipt	6	DELETE	test-script	2026-08-12 11:31:47.057864	{"po_id": 3, "file_path": null, "vendor_id": 15, "grn_number": "TEST-GRN-0002", "receipt_date": "2026-08-06"}	null
67	purchase_order	3	DELETE	test-script	2026-08-12 11:31:47.430679	{"po_date": "2026-08-01", "subtotal": "500.00", "file_path": null, "po_number": "TEST-PO-0001", "status_id": 14, "vendor_id": 15, "tax_amount": "180.00", "currency_id": 1, "total_amount": "1180.00", "expected_delivery_date": "2026-08-15"}	null
68	purchase_order	4	CREATE	1	2026-08-12 12:34:50.781493	null	{"po_date": "2026-08-12", "subtotal": "100000", "file_path": null, "po_number": "PO-2026-001", "status_id": 14, "vendor_id": 16, "tax_amount": "18000", "currency_id": 1, "total_amount": "118000", "expected_delivery_date": "2026-08-25"}
69	goods_receipt	8	CREATE	1	2026-08-12 12:36:37.7362	null	{"po_id": null, "file_path": null, "vendor_id": 16, "grn_number": "GRN-2026-001", "receipt_date": "2026-08-12"}
70	goods_receipt	11	CREATE	1	2026-08-12 12:53:58.4716	null	{"po_id": 4, "file_path": null, "vendor_id": 16, "grn_number": "GRN-2026-002", "receipt_date": "2026-08-12"}
\.


--
-- Data for Name: country; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.country (country_id, country_name, country_code, is_active, created_at) FROM stdin;
1	India	IN	t	2026-07-22 19:22:11.117003
2	United States	US	f	2026-07-22 19:22:11.117003
3	Germany	DE	f	2026-07-22 19:22:11.117003
4	United Arab Emirates	AE	f	2026-07-22 19:22:11.117003
5	Singapore	SG	f	2026-07-22 19:22:11.117003
\.


--
-- Data for Name: currency; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.currency (currency_id, currency_name, currency_code, symbol, decimal_places, is_active, created_at) FROM stdin;
1	Indian Rupee	INR	₹	2	t	2026-07-22 19:22:11.117003
2	US Dollar	USD	$	2	t	2026-07-22 19:22:11.117003
3	Euro	EUR	€	2	t	2026-07-22 19:22:11.117003
\.


--
-- Data for Name: goods_receipt; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.goods_receipt (grn_id, po_id, vendor_id, file_path, created_by, created_at, grn_number, receipt_date) FROM stdin;
1	1	16	\N	1	2026-08-12 09:17:12.087555	\N	\N
7	\N	15	\N	test-script	2026-08-12 11:31:46.391666	\N	\N
8	\N	16	\N	1	2026-08-12 12:36:37.7362	GRN-2026-001	2026-08-12
11	4	16	\N	1	2026-08-12 12:53:58.4716	GRN-2026-002	2026-08-12
\.


--
-- Data for Name: goods_receipt_line; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.goods_receipt_line (grn_line_id, grn_id, description, received_quantity, po_line_id, item_code) FROM stdin;
7	8	Business Laptop	5.0000	\N	\N
8	11	Business Laptop	5.0000	7	\N
\.


--
-- Data for Name: inbound_document; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.inbound_document (inbound_document_id, source_type, email_from, email_subject, email_message_id, received_at, file_name, file_path, extraction_status, extraction_confidence, raw_extracted_data, vendor_id, invoice_id, created_at) FROM stdin;
1	UPLOAD	\N	\N	\N	2026-08-10 16:18:47.006694	aws-gst-invoice-may-2026.pdf	invoices/2026/08/0a97685cdd834c97887258139bb77b9f_aws-gst-invoice-may-2026.pdf	FAILED	\N	\N	\N	\N	2026-08-10 16:18:47.006694
2	UPLOAD	\N	\N	\N	2026-08-10 16:40:56.539401	aws-gst-invoice-may-2026.pdf	invoices/2026/08/16209b00009046918358948b68ff1d25_aws-gst-invoice-may-2026.pdf	PENDING	\N	\N	\N	\N	2026-08-10 16:40:56.539401
3	UPLOAD	\N	\N	\N	2026-08-10 16:44:14.998542	aws-gst-invoice-may-2026.pdf	invoices/2026/08/0d50621eae644dd686c132505a7e2247_aws-gst-invoice-may-2026.pdf	EXTRACTED	80.23	{"cess": null, "cgst": null, "igst": "598.07", "sgst": null, "gstin": "07AAJCA9880A1ZL", "lines": [], "total": "3605.75", "currency": "INR", "due_date": null, "subtotal": "266.91", "tax_rate": null, "tax_type": null, "po_number": null, "tax_amount": null, "buyer_gstin": null, "vendor_name": "Amazon Web Services India Private Limited", "invoice_date": "2026-06-02", "payment_terms": null, "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "igst": {"page": 2, "value": "598.07", "method": "ANCHOR+GEOMETRY+SAME_LINE+AGGREGATED", "confidence": 63.0, "matched_anchor": "IGST"}, "sgst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "gstin": {"page": 1, "value": "07AAJCA9880A1ZL", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "GST Number"}, "total": {"page": 1, "value": "3605.75", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 87.0, "matched_anchor": "TOTAL AMOUNT"}, "currency": {"page": 1, "value": "INR", "method": "GEOMETRY+NEAREST", "confidence": 45.0, "matched_anchor": null}, "due_date": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "subtotal": {"page": 2, "value": "266.91", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "Net Charges"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "vendor_name": {"page": 1, "value": "Amazon Web Services India Private Limited", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "from"}, "invoice_date": {"page": 1, "value": "2026-06-02", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Invoice Date"}, "payment_terms": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "invoice_number": {"page": 1, "value": "AIN2627000969471", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Invoice Number"}}, "invoice_number": "AIN2627000969471", "field_confidences": {"cess": 0.0, "cgst": 0.0, "igst": 63.0, "sgst": 0.0, "gstin": 75.0, "total": 87.0, "currency": 45.0, "due_date": 0.0, "subtotal": 83.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 0.0, "tax_amount": 0.0, "buyer_gstin": 0.0, "vendor_name": 75.0, "invoice_date": 75.0, "payment_terms": 0.0, "invoice_number": 75.0}}	15	1	2026-08-10 16:44:14.998542
4	UPLOAD	\N	\N	\N	2026-08-11 09:04:55.613859	invoice.jpg	invoices/2026/08/4f9920fcd71b42888802b8da53acf437_invoice.jpg	EXTRACTED	54.32	{"cess": null, "cgst": "852.88", "igst": "0.00", "sgst": "852.88", "gstin": "24ASWBD4582Q1ZW", "lines": [{"quantity": "10", "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": null, "unit_price": null, "description": "Electronics Product Name", "line_amount": "1500", "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": null, "unit_price": "2500", "description": "ItemDetails", "line_amount": "12500", "line_number": 2}], "total": "35821.00", "currency": "INR", "due_date": null, "subtotal": "34115.00", "tax_rate": null, "tax_type": null, "po_number": null, "tax_amount": null, "buyer_gstin": null, "vendor_name": "Manan Agency", "invoice_date": "2020-03-24", "payment_terms": null, "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "852.88", "method": "ANCHOR+BELOW+GEOMETRY", "confidence": 58.0, "matched_anchor": "CGST"}, "igst": {"page": 1, "value": "0.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "IGST"}, "sgst": {"page": 1, "value": "852.88", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "SGST"}, "gstin": {"page": 1, "value": "24ASWBD4582Q1ZW", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "GSTIN"}, "total": {"page": 1, "value": "35821.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "Total Amount"}, "currency": {"page": 1, "value": "INR", "method": "NEAREST+REGEX", "confidence": 16.0, "matched_anchor": null}, "due_date": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "subtotal": {"page": 1, "value": "34115.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "Basic Amount"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "vendor_name": {"page": 1, "value": "Manan Agency", "method": "FALLBACK+GEOMETRY", "confidence": 63.0, "matched_anchor": null}, "invoice_date": {"page": 1, "value": "2020-03-24", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Date"}, "payment_terms": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "invoice_number": {"page": 1, "value": "46", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Invoice No"}}, "invoice_number": "46", "field_confidences": {"cess": 0.0, "cgst": 58.0, "igst": 83.0, "sgst": 83.0, "gstin": 75.0, "total": 95.0, "currency": 16.0, "due_date": 0.0, "subtotal": 83.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 0.0, "tax_amount": 0.0, "buyer_gstin": 0.0, "vendor_name": 63.0, "invoice_date": 75.0, "payment_terms": 0.0, "invoice_number": 75.0}}	\N	\N	2026-08-11 09:04:55.613859
5	UPLOAD	\N	\N	\N	2026-08-11 12:06:48.735566	invoice_02.pdf	invoices/2026/08/820d6ad8e947438ebb3a85339fe4a6e1_invoice_02.pdf	FAILED	56.59	{"cess": null, "cgst": "140000.00", "igst": null, "sgst": "140000.00", "gstin": "36AABCT1234F1Z5", "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Annual ERP Software Subscription -", "line_amount": null, "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Implementation and Configuration", "line_amount": null, "line_number": 2}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Technical Support and Maintenance", "line_amount": null, "line_number": 3}], "total": "165200.00", "currency": "INR", "due_date": null, "subtotal": "140000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-45001234", "tax_amount": null, "buyer_gstin": "36AACCA5678G1Z2", "vendor_name": "TECHNOVA SOLUTIONS PRIVATE LIMITED", "invoice_date": null, "payment_terms": "Net 30", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "SGST"}, "gstin": {"page": 1, "value": "36AABCT1234F1Z5", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "GSTIN"}, "total": {"page": 1, "value": "165200.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 87.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "NEAREST+REGEX", "confidence": 16.0, "matched_anchor": null}, "due_date": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "subtotal": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-45001234", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "36AACCA5678G1Z2", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "TECHNOVA SOLUTIONS PRIVATE LIMITED", "method": "FALLBACK+GEOMETRY", "confidence": 63.0, "matched_anchor": null}, "invoice_date": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "payment_terms": {"page": 1, "value": "Net 30", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "INV-2026-00871", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Invoice No."}}, "invoice_number": "INV-2026-00871", "field_confidences": {"cess": 0.0, "cgst": 83.0, "igst": 0.0, "sgst": 83.0, "gstin": 75.0, "total": 87.0, "currency": 16.0, "due_date": 0.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 75.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 63.0, "invoice_date": 0.0, "payment_terms": 75.0, "invoice_number": 75.0}}	\N	\N	2026-08-11 12:06:48.735566
6	UPLOAD	\N	\N	\N	2026-08-11 12:07:13.996647	invoice_02.pdf	invoices/2026/08/786c2fc4b7494f47990690780293e4e0_invoice_02.pdf	FAILED	56.59	{"cess": null, "cgst": "140000.00", "igst": null, "sgst": "140000.00", "gstin": "36AABCT1234F1Z5", "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Annual ERP Software Subscription -", "line_amount": null, "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Implementation and Configuration", "line_amount": null, "line_number": 2}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Technical Support and Maintenance", "line_amount": null, "line_number": 3}], "total": "165200.00", "currency": "INR", "due_date": null, "subtotal": "140000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-45001234", "tax_amount": null, "buyer_gstin": "36AACCA5678G1Z2", "vendor_name": "TECHNOVA SOLUTIONS PRIVATE LIMITED", "invoice_date": null, "payment_terms": "Net 30", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "SGST"}, "gstin": {"page": 1, "value": "36AABCT1234F1Z5", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "GSTIN"}, "total": {"page": 1, "value": "165200.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 87.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "NEAREST+REGEX", "confidence": 16.0, "matched_anchor": null}, "due_date": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "subtotal": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-45001234", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "36AACCA5678G1Z2", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "TECHNOVA SOLUTIONS PRIVATE LIMITED", "method": "FALLBACK+GEOMETRY", "confidence": 63.0, "matched_anchor": null}, "invoice_date": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "payment_terms": {"page": 1, "value": "Net 30", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "INV-2026-00871", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Invoice No."}}, "invoice_number": "INV-2026-00871", "field_confidences": {"cess": 0.0, "cgst": 83.0, "igst": 0.0, "sgst": 83.0, "gstin": 75.0, "total": 87.0, "currency": 16.0, "due_date": 0.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 75.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 63.0, "invoice_date": 0.0, "payment_terms": 75.0, "invoice_number": 75.0}}	\N	\N	2026-08-11 12:07:13.996647
7	UPLOAD	\N	\N	\N	2026-08-11 12:07:25.760621	invoice_01.pdf	invoices/2026/08/4f005a775435427aa917a9b05a412244_invoice_01.pdf	FAILED	53.98	{"cess": null, "cgst": "11250.00", "igst": null, "sgst": "11250.00", "gstin": null, "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": "85000.00", "unit_price": "1", "description": "Software Development", "line_amount": "15300.00", "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": "25000.00", "unit_price": "1", "description": "Application Support &", "line_amount": "4500.00", "line_number": 2}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": "15000.00", "unit_price": "1", "description": "Cloud Infrastructure Support", "line_amount": "2700.00", "line_number": 3}], "total": "147500.00", "currency": "INR", "due_date": null, "subtotal": "125000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-XYZ-2026-0189", "tax_amount": null, "buyer_gstin": "29AABCA1234F1Z5", "vendor_name": "ABC TECHNOLOGIES PRIVATE LIMITED", "invoice_date": null, "payment_terms": "Net 30 Days", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "11250.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "11250.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "SGST"}, "gstin": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "total": {"page": 1, "value": "147500.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 87.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "GEOMETRY+NEAREST", "confidence": 30.0, "matched_anchor": null}, "due_date": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "subtotal": {"page": 1, "value": "125000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-XYZ-2026-0189", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "29AABCA1234F1Z5", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "ABC TECHNOLOGIES PRIVATE LIMITED", "method": "FALLBACK+GEOMETRY", "confidence": 63.0, "matched_anchor": null}, "invoice_date": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "payment_terms": {"page": 1, "value": "Net 30 Days", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "ALL", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "invoice number"}}, "invoice_number": "ALL", "field_confidences": {"cess": 0.0, "cgst": 75.0, "igst": 0.0, "sgst": 75.0, "gstin": 0.0, "total": 87.0, "currency": 30.0, "due_date": 0.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 55.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 63.0, "invoice_date": 0.0, "payment_terms": 75.0, "invoice_number": 75.0}}	\N	\N	2026-08-11 12:07:25.760621
8	UPLOAD	\N	\N	\N	2026-08-11 12:25:12.910951	invoice_01.pdf	invoices/2026/08/a95368b0d257407e94f13e27c18050a7_invoice_01.pdf	FAILED	\N	\N	\N	\N	2026-08-11 12:25:12.910951
9	UPLOAD	\N	\N	\N	2026-08-11 12:27:17.156604	invoice_01.pdf	invoices/2026/08/9aa3db55c1b844faa6c9b09c7e084ee7_invoice_01.pdf	FAILED	53.98	{"cess": null, "cgst": "11250.00", "igst": null, "sgst": "11250.00", "gstin": null, "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": "85000.00", "unit_price": "1", "description": "Software Development", "line_amount": "15300.00", "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": "25000.00", "unit_price": "1", "description": "Application Support &", "line_amount": "4500.00", "line_number": 2}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": "15000.00", "unit_price": "1", "description": "Cloud Infrastructure Support", "line_amount": "2700.00", "line_number": 3}], "total": "147500.00", "currency": "INR", "due_date": null, "subtotal": "125000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-XYZ-2026-0189", "tax_amount": null, "buyer_gstin": "29AABCA1234F1Z5", "vendor_name": "ABC TECHNOLOGIES PRIVATE LIMITED", "invoice_date": null, "payment_terms": "Net 30 Days", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "11250.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "11250.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "SGST"}, "gstin": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "total": {"page": 1, "value": "147500.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 87.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "GEOMETRY+NEAREST", "confidence": 30.0, "matched_anchor": null}, "due_date": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "subtotal": {"page": 1, "value": "125000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-XYZ-2026-0189", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "29AABCA1234F1Z5", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "ABC TECHNOLOGIES PRIVATE LIMITED", "method": "FALLBACK+GEOMETRY", "confidence": 63.0, "matched_anchor": null}, "invoice_date": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "payment_terms": {"page": 1, "value": "Net 30 Days", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "ALL", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "invoice number"}}, "invoice_number": "ALL", "field_confidences": {"cess": 0.0, "cgst": 75.0, "igst": 0.0, "sgst": 75.0, "gstin": 0.0, "total": 87.0, "currency": 30.0, "due_date": 0.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 55.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 63.0, "invoice_date": 0.0, "payment_terms": 75.0, "invoice_number": 75.0}}	\N	\N	2026-08-11 12:27:17.156604
10	UPLOAD	\N	\N	\N	2026-08-11 12:30:30.686685	invoice_01.pdf	invoices/2026/08/ca6329c1054b440093ee060252aa1726_invoice_01.pdf	FAILED	53.98	{"cess": null, "cgst": "11250.00", "igst": null, "sgst": "11250.00", "gstin": null, "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": "85000.00", "unit_price": "1", "description": "Software Development", "line_amount": "15300.00", "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": "25000.00", "unit_price": "1", "description": "Application Support &", "line_amount": "4500.00", "line_number": 2}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": "15000.00", "unit_price": "1", "description": "Cloud Infrastructure Support", "line_amount": "2700.00", "line_number": 3}], "total": "147500.00", "currency": "INR", "due_date": null, "subtotal": "125000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-XYZ-2026-0189", "tax_amount": null, "buyer_gstin": "29AABCA1234F1Z5", "vendor_name": "ABC TECHNOLOGIES PRIVATE LIMITED", "invoice_date": null, "payment_terms": "Net 30 Days", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "11250.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "11250.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "SGST"}, "gstin": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "total": {"page": 1, "value": "147500.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 87.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "GEOMETRY+NEAREST", "confidence": 30.0, "matched_anchor": null}, "due_date": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "subtotal": {"page": 1, "value": "125000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-XYZ-2026-0189", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "29AABCA1234F1Z5", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "ABC TECHNOLOGIES PRIVATE LIMITED", "method": "FALLBACK+GEOMETRY", "confidence": 63.0, "matched_anchor": null}, "invoice_date": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "payment_terms": {"page": 1, "value": "Net 30 Days", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "ALL", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "invoice number"}}, "invoice_number": "ALL", "field_confidences": {"cess": 0.0, "cgst": 75.0, "igst": 0.0, "sgst": 75.0, "gstin": 0.0, "total": 87.0, "currency": 30.0, "due_date": 0.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 55.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 63.0, "invoice_date": 0.0, "payment_terms": 75.0, "invoice_number": 75.0}}	\N	\N	2026-08-11 12:30:30.686685
11	UPLOAD	\N	\N	\N	2026-08-11 12:32:37.102238	invoice_01.pdf	invoices/2026/08/324c78abb83b45399a3dd3496d0afcf8_invoice_01.pdf	EXTRACTED	60.38	{"cess": null, "cgst": "11250.00", "igst": null, "sgst": "11250.00", "gstin": null, "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": "85000.00", "unit_price": "1", "description": "Software Development", "line_amount": "15300.00", "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": "25000.00", "unit_price": "1", "description": "Application Support &", "line_amount": "4500.00", "line_number": 2}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": "15000.00", "unit_price": "1", "description": "Cloud Infrastructure Support", "line_amount": "2700.00", "line_number": 3}], "total": "147500.00", "currency": "INR", "due_date": "2026-09-10", "subtotal": "125000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-XYZ-2026-0189", "tax_amount": null, "buyer_gstin": "29AABCA1234F1Z5", "vendor_name": "ABC TECHNOLOGIES PRIVATE LIMITED", "invoice_date": "2026-08-11", "payment_terms": "Net 30 Days", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "11250.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "11250.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "SGST"}, "gstin": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "total": {"page": 1, "value": "147500.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 87.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "GEOMETRY+NEAREST", "confidence": 30.0, "matched_anchor": null}, "due_date": {"page": 1, "value": "2026-09-10", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Due Date"}, "subtotal": {"page": 1, "value": "125000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-XYZ-2026-0189", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "29AABCA1234F1Z5", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "ABC TECHNOLOGIES PRIVATE LIMITED", "method": "FALLBACK+GEOMETRY", "confidence": 63.0, "matched_anchor": null}, "invoice_date": {"page": 1, "value": "2026-08-11", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Invoice Date"}, "payment_terms": {"page": 1, "value": "Net 30 Days", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "ALL", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "invoice number"}}, "invoice_number": "ALL", "field_confidences": {"cess": 0.0, "cgst": 75.0, "igst": 0.0, "sgst": 75.0, "gstin": 0.0, "total": 87.0, "currency": 30.0, "due_date": 55.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 55.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 63.0, "invoice_date": 55.0, "payment_terms": 75.0, "invoice_number": 75.0}}	\N	\N	2026-08-11 12:32:37.102238
12	UPLOAD	\N	\N	\N	2026-08-11 12:36:05.759918	invoice_02.pdf	invoices/2026/08/c5b427497458443094ea813293ba4676_invoice_02.pdf	EXTRACTED	63.80	{"cess": null, "cgst": "140000.00", "igst": null, "sgst": "140000.00", "gstin": "36AABCT1234F1Z5", "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Annual ERP Software Subscription -", "line_amount": null, "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Implementation and Configuration", "line_amount": null, "line_number": 2}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Technical Support and Maintenance", "line_amount": null, "line_number": 3}], "total": "165200.00", "currency": "INR", "due_date": "2026-09-10", "subtotal": "140000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-45001234", "tax_amount": null, "buyer_gstin": "36AACCA5678G1Z2", "vendor_name": "TECHNOVA SOLUTIONS PRIVATE LIMITED", "invoice_date": "2026-08-11", "payment_terms": "Net 30", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "SGST"}, "gstin": {"page": 1, "value": "36AABCT1234F1Z5", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "GSTIN"}, "total": {"page": 1, "value": "165200.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 87.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "NEAREST+REGEX", "confidence": 16.0, "matched_anchor": null}, "due_date": {"page": 1, "value": "2026-09-10", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Due Date"}, "subtotal": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-45001234", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "36AACCA5678G1Z2", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "TECHNOVA SOLUTIONS PRIVATE LIMITED", "method": "FALLBACK+GEOMETRY", "confidence": 63.0, "matched_anchor": null}, "invoice_date": {"page": 1, "value": "2026-08-11", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Invoice Date"}, "payment_terms": {"page": 1, "value": "Net 30", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "INV-2026-00871", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Invoice No."}}, "invoice_number": "INV-2026-00871", "field_confidences": {"cess": 0.0, "cgst": 83.0, "igst": 0.0, "sgst": 83.0, "gstin": 75.0, "total": 87.0, "currency": 16.0, "due_date": 75.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 75.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 63.0, "invoice_date": 75.0, "payment_terms": 75.0, "invoice_number": 75.0}}	\N	\N	2026-08-11 12:36:05.759918
13	UPLOAD	\N	\N	\N	2026-08-11 12:46:12.28939	invoice_02.pdf	invoices/2026/08/5bdbd3f58be840419125e7080954c96c_invoice_02.pdf	EXTRACTED	63.80	{"cess": null, "cgst": "140000.00", "igst": null, "sgst": "140000.00", "gstin": "36AABCT1234F1Z5", "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Annual ERP Software Subscription -", "line_amount": null, "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Implementation and Configuration", "line_amount": null, "line_number": 2}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Technical Support and Maintenance", "line_amount": null, "line_number": 3}], "total": "165200.00", "currency": "INR", "due_date": "2026-09-10", "subtotal": "140000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-45001234", "tax_amount": null, "buyer_gstin": "36AACCA5678G1Z2", "vendor_name": "TECHNOVA SOLUTIONS PRIVATE LIMITED", "invoice_date": "2026-08-11", "payment_terms": "Net 30", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "SGST"}, "gstin": {"page": 1, "value": "36AABCT1234F1Z5", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "GSTIN"}, "total": {"page": 1, "value": "165200.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 87.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "NEAREST+REGEX", "confidence": 16.0, "matched_anchor": null}, "due_date": {"page": 1, "value": "2026-09-10", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Due Date"}, "subtotal": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-45001234", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "36AACCA5678G1Z2", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "TECHNOVA SOLUTIONS PRIVATE LIMITED", "method": "FALLBACK+GEOMETRY", "confidence": 63.0, "matched_anchor": null}, "invoice_date": {"page": 1, "value": "2026-08-11", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Invoice Date"}, "payment_terms": {"page": 1, "value": "Net 30", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "INV-2026-00871", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Invoice No."}}, "invoice_number": "INV-2026-00871", "field_confidences": {"cess": 0.0, "cgst": 83.0, "igst": 0.0, "sgst": 83.0, "gstin": 75.0, "total": 87.0, "currency": 16.0, "due_date": 75.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 75.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 63.0, "invoice_date": 75.0, "payment_terms": 75.0, "invoice_number": 75.0}}	\N	\N	2026-08-11 12:46:12.28939
14	UPLOAD	\N	\N	\N	2026-08-11 12:57:05.081672	invoice_02.pdf	invoices/2026/08/d4433776659344aaae52e6b52d5a0af9_invoice_02.pdf	EXTRACTED	63.80	{"cess": null, "cgst": "140000.00", "igst": null, "sgst": "140000.00", "gstin": "36AABCT1234F1Z5", "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Annual ERP Software Subscription -", "line_amount": null, "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Implementation and Configuration", "line_amount": null, "line_number": 2}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.5, "tax_amount": null, "unit_price": "1", "description": "Technical Support and Maintenance", "line_amount": null, "line_number": 3}], "total": "165200.00", "currency": "INR", "due_date": "2026-09-10", "subtotal": "140000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-45001234", "tax_amount": null, "buyer_gstin": "36AACCA5678G1Z2", "vendor_name": "TECHNOVA SOLUTIONS PRIVATE LIMITED", "invoice_date": "2026-08-11", "payment_terms": "Net 30", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 83.0, "matched_anchor": "SGST"}, "gstin": {"page": 1, "value": "36AABCT1234F1Z5", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "GSTIN"}, "total": {"page": 1, "value": "165200.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 87.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "NEAREST+REGEX", "confidence": 16.0, "matched_anchor": null}, "due_date": {"page": 1, "value": "2026-09-10", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Due Date"}, "subtotal": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-45001234", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "36AACCA5678G1Z2", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "TECHNOVA SOLUTIONS PRIVATE LIMITED", "method": "FALLBACK+GEOMETRY", "confidence": 63.0, "matched_anchor": null}, "invoice_date": {"page": 1, "value": "2026-08-11", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Invoice Date"}, "payment_terms": {"page": 1, "value": "Net 30", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "INV-2026-00871", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Invoice No."}}, "invoice_number": "INV-2026-00871", "field_confidences": {"cess": 0.0, "cgst": 83.0, "igst": 0.0, "sgst": 83.0, "gstin": 75.0, "total": 87.0, "currency": 16.0, "due_date": 75.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 75.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 63.0, "invoice_date": 75.0, "payment_terms": 75.0, "invoice_number": 75.0}}	\N	\N	2026-08-11 12:57:05.081672
15	UPLOAD	\N	\N	\N	2026-08-11 13:00:24.925015	invoice_02.pdf	invoices/2026/08/6bbabdc2fe7a4cdb931bdf35441e8154_invoice_02.pdf	PENDING	\N	\N	\N	\N	2026-08-11 13:00:24.925015
16	UPLOAD	\N	\N	\N	2026-08-11 13:18:25.664447	keka_gst_invoice_text_pdf.pdf	invoices/2026/08/62650bd5259b4baeb172e96ecc3faf19_keka_gst_invoice_text_pdf.pdf	PENDING	\N	\N	\N	\N	2026-08-11 13:18:25.664447
17	UPLOAD	\N	\N	\N	2026-08-11 13:20:28.246407	keka_gst_invoice_text_pdf.pdf	invoices/2026/08/d2340c527ae04e7ab5fb2e415aa3ced9_keka_gst_invoice_text_pdf.pdf	PENDING	\N	\N	\N	\N	2026-08-11 13:20:28.246407
18	UPLOAD	\N	\N	\N	2026-08-11 13:28:14.030738	keka_gst_invoice_text_pdf.pdf	invoices/2026/08/5fb3f7b3bcf84aaab116ec6019c67b35_keka_gst_invoice_text_pdf.pdf	EXTRACTED	54.15	{"cess": null, "cgst": "12600.00", "igst": null, "sgst": "165200.00", "gstin": null, "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": null, "unit_price": "1", "description": "HR & Employee Experience Software", "line_amount": "100000.00", "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": null, "unit_price": "1", "description": "Implementation and Professional", "line_amount": "40000.00", "line_number": 2}], "total": "165200.00", "currency": "INR", "due_date": "2026-09-10", "subtotal": "140000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-45001234", "tax_amount": null, "buyer_gstin": "36AAFCK5835K1Z6", "vendor_name": "Apex Business Solutions Private Limited", "invoice_date": "2026-08-11", "payment_terms": "Net 30 Days", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "12600.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "165200.00", "method": "ANCHOR+BELOW+GEOMETRY", "confidence": 58.0, "matched_anchor": "SGST"}, "gstin": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "total": {"page": 1, "value": "165200.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "GEOMETRY+NEAREST", "confidence": 30.0, "matched_anchor": null}, "due_date": {"page": 1, "value": "2026-09-10", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Due Date"}, "subtotal": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-45001234", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "36AAFCK5835K1Z6", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "method": "FALLBACK+GEOMETRY", "confidence": 43.0, "matched_anchor": null}, "invoice_date": {"page": 1, "value": "2026-08-11", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Invoice Date"}, "payment_terms": {"page": 1, "value": "Net 30 Days", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "INV-2026-00871", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Invoice No."}}, "invoice_number": "INV-2026-00871", "field_confidences": {"cess": 0.0, "cgst": 75.0, "igst": 0.0, "sgst": 58.0, "gstin": 0.0, "total": 95.0, "currency": 30.0, "due_date": 55.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 55.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 43.0, "invoice_date": 55.0, "payment_terms": 75.0, "invoice_number": 55.0}}	\N	\N	2026-08-11 13:28:14.030738
19	UPLOAD	\N	\N	\N	2026-08-11 13:29:37.233673	keka_gst_invoice_text_pdf.pdf	invoices/2026/08/45c11a3c73df4a868922bd230babbdcb_keka_gst_invoice_text_pdf.pdf	EXTRACTED	54.15	{"cess": null, "cgst": "12600.00", "igst": null, "sgst": "165200.00", "gstin": null, "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": null, "unit_price": "1", "description": "HR & Employee Experience Software", "line_amount": "100000.00", "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": null, "unit_price": "1", "description": "Implementation and Professional", "line_amount": "40000.00", "line_number": 2}], "total": "165200.00", "currency": "INR", "due_date": "2026-09-10", "subtotal": "140000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-45001234", "tax_amount": null, "buyer_gstin": "36AAFCK5835K1Z6", "vendor_name": "Apex Business Solutions Private Limited", "invoice_date": "2026-08-11", "payment_terms": "Net 30 Days", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "12600.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "165200.00", "method": "ANCHOR+BELOW+GEOMETRY", "confidence": 58.0, "matched_anchor": "SGST"}, "gstin": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "total": {"page": 1, "value": "165200.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "GEOMETRY+NEAREST", "confidence": 30.0, "matched_anchor": null}, "due_date": {"page": 1, "value": "2026-09-10", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Due Date"}, "subtotal": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-45001234", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "36AAFCK5835K1Z6", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "method": "FALLBACK+GEOMETRY", "confidence": 43.0, "matched_anchor": null}, "invoice_date": {"page": 1, "value": "2026-08-11", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Invoice Date"}, "payment_terms": {"page": 1, "value": "Net 30 Days", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "INV-2026-00871", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Invoice No."}}, "invoice_number": "INV-2026-00871", "field_confidences": {"cess": 0.0, "cgst": 75.0, "igst": 0.0, "sgst": 58.0, "gstin": 0.0, "total": 95.0, "currency": 30.0, "due_date": 55.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 55.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 43.0, "invoice_date": 55.0, "payment_terms": 75.0, "invoice_number": 55.0}}	\N	\N	2026-08-11 13:29:37.233673
20	UPLOAD	\N	\N	\N	2026-08-11 13:31:56.010345	keka_gst_invoice_text_pdf.pdf	invoices/2026/08/20bc07cb94094223bdf8cf21961096de_keka_gst_invoice_text_pdf.pdf	EXTRACTED	54.15	{"cess": null, "cgst": "12600.00", "igst": null, "sgst": "165200.00", "gstin": null, "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": null, "unit_price": "1", "description": "HR & Employee Experience Software", "line_amount": "100000.00", "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": null, "unit_price": "1", "description": "Implementation and Professional", "line_amount": "40000.00", "line_number": 2}], "total": "165200.00", "currency": "INR", "due_date": "2026-09-10", "subtotal": "140000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-45001234", "tax_amount": null, "buyer_gstin": "36AAFCK5835K1Z6", "vendor_name": "Apex Business Solutions Private Limited", "invoice_date": "2026-08-11", "payment_terms": "Net 30 Days", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "12600.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "165200.00", "method": "ANCHOR+BELOW+GEOMETRY", "confidence": 58.0, "matched_anchor": "SGST"}, "gstin": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "total": {"page": 1, "value": "165200.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "GEOMETRY+NEAREST", "confidence": 30.0, "matched_anchor": null}, "due_date": {"page": 1, "value": "2026-09-10", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Due Date"}, "subtotal": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-45001234", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "36AAFCK5835K1Z6", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "method": "FALLBACK+GEOMETRY", "confidence": 43.0, "matched_anchor": null}, "invoice_date": {"page": 1, "value": "2026-08-11", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Invoice Date"}, "payment_terms": {"page": 1, "value": "Net 30 Days", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "INV-2026-00871", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Invoice No."}}, "invoice_number": "INV-2026-00871", "field_confidences": {"cess": 0.0, "cgst": 75.0, "igst": 0.0, "sgst": 58.0, "gstin": 0.0, "total": 95.0, "currency": 30.0, "due_date": 55.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 55.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 43.0, "invoice_date": 55.0, "payment_terms": 75.0, "invoice_number": 55.0}}	\N	\N	2026-08-11 13:31:56.010345
21	UPLOAD	\N	\N	\N	2026-08-11 13:33:19.782226	keka_gst_invoice_text_pdf.pdf	invoices/2026/08/2df92545788643d1837f395b1c3c9c90_keka_gst_invoice_text_pdf.pdf	EXTRACTED	54.15	{"cess": null, "cgst": "12600.00", "igst": null, "sgst": "165200.00", "gstin": null, "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": null, "unit_price": "1", "description": "HR & Employee Experience Software", "line_amount": "100000.00", "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": null, "unit_price": "1", "description": "Implementation and Professional", "line_amount": "40000.00", "line_number": 2}], "total": "165200.00", "currency": "INR", "due_date": "2026-09-10", "subtotal": "140000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-45001234", "tax_amount": null, "buyer_gstin": "36AAFCK5835K1Z6", "vendor_name": "Apex Business Solutions Private Limited", "invoice_date": "2026-08-11", "payment_terms": "Net 30 Days", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "12600.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "165200.00", "method": "ANCHOR+BELOW+GEOMETRY", "confidence": 58.0, "matched_anchor": "SGST"}, "gstin": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "total": {"page": 1, "value": "165200.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "GEOMETRY+NEAREST", "confidence": 30.0, "matched_anchor": null}, "due_date": {"page": 1, "value": "2026-09-10", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Due Date"}, "subtotal": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-45001234", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "36AAFCK5835K1Z6", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "method": "FALLBACK+GEOMETRY", "confidence": 43.0, "matched_anchor": null}, "invoice_date": {"page": 1, "value": "2026-08-11", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Invoice Date"}, "payment_terms": {"page": 1, "value": "Net 30 Days", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "INV-2026-00871", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Invoice No."}}, "invoice_number": "INV-2026-00871", "field_confidences": {"cess": 0.0, "cgst": 75.0, "igst": 0.0, "sgst": 58.0, "gstin": 0.0, "total": 95.0, "currency": 30.0, "due_date": 55.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 55.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 43.0, "invoice_date": 55.0, "payment_terms": 75.0, "invoice_number": 55.0}}	\N	\N	2026-08-11 13:33:19.782226
\.


--
-- Data for Name: invoice; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.invoice (invoice_id, invoice_number, vendor_id, inbound_document_id, invoice_type, po_id, grn_id, invoice_date, due_date, payment_term_id, currency_id, gross_amount, discount_amount, tax_amount, net_amount, amount_paid, status_id, created_by, created_at, updated_by, updated_at) FROM stdin;
1	AIN2627000969471	15	3	NON_PO	\N	\N	2026-06-02	2026-06-02	\N	1	266.91	0.00	598.07	3605.75	0.00	6	5100031	2026-08-10 16:44:15.106618	5100031	2026-08-10 16:44:15.106618
\.


--
-- Data for Name: invoice_approval; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.invoice_approval (invoice_approval_id, invoice_id, invoice_issue_id, approver_name, decision, comments, decided_at, created_at) FROM stdin;
\.


--
-- Data for Name: invoice_attachment; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.invoice_attachment (invoice_attachment_id, invoice_id, file_name, file_path, uploaded_at) FROM stdin;
1	1	aws-gst-invoice-may-2026.pdf	invoices/2026/08/0d50621eae644dd686c132505a7e2247_aws-gst-invoice-may-2026.pdf	2026-08-10 16:44:15.106618
\.


--
-- Data for Name: invoice_issue; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.invoice_issue (invoice_issue_id, invoice_id, issue_source, issue_type, severity, result, description, status_id, resolved_by, resolved_at, created_at) FROM stdin;
1	1	VALIDATION	VALIDATION_FAILED	WARNING	\N	Total 3605.75 does not match subtotal + taxes 864.98 (tolerance 1.00)	\N	\N	\N	2026-08-10 16:44:15.106618
\.


--
-- Data for Name: invoice_line; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.invoice_line (invoice_line_id, invoice_id, line_number, description, quantity, unit_price, line_amount, tax_type_id, tax_amount) FROM stdin;
\.


--
-- Data for Name: payment; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.payment (payment_id, vendor_id, vendor_bank_id, scheduled_date, payment_date, total_amount, currency_id, payment_method, reference_number, status_id, created_by, created_at, updated_by, updated_at) FROM stdin;
\.


--
-- Data for Name: payment_invoice; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.payment_invoice (payment_invoice_id, payment_id, invoice_id, allocated_amount, created_at) FROM stdin;
\.


--
-- Data for Name: payment_term; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.payment_term (payment_term_id, term_name, due_days, discount_percent, discount_days, is_system_default, is_active, created_by, created_at, updated_by, updated_at) FROM stdin;
1	Immediate	0	0.00	0	t	t	\N	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
2	Net 15	15	0.00	0	t	t	\N	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
3	Net 30	30	2.00	10	t	t	\N	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
4	Net 45	45	0.00	0	t	t	\N	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
5	Net 60	60	0.00	0	t	t	\N	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
\.


--
-- Data for Name: purchase_order; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.purchase_order (po_id, po_number, vendor_id, file_path, status_id, created_by, created_at, po_date, expected_delivery_date, currency_id, subtotal, tax_amount, total_amount) FROM stdin;
1	PO-TEST-001	16	invoices/2026/08/54728085edd449f581175e70f10c5291_invoice_1.pdf	14	1	2026-08-12 07:36:44.227842	\N	\N	\N	\N	\N	\N
4	PO-2026-001	16	\N	14	1	2026-08-12 12:34:50.781493	2026-08-12	2026-08-25	1	100000.00	18000.00	118000.00
\.


--
-- Data for Name: purchase_order_line; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.purchase_order_line (po_line_id, po_id, description, quantity, unit_price, tax_amount, line_amount, item_code) FROM stdin;
7	4	Business Laptop	5.0000	20000.0000	18000.00	118000.00	LAP-001
\.


--
-- Data for Name: status_master; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.status_master (status_id, module_name, status_code, status_name, display_order) FROM stdin;
1	VENDOR	PENDING	Pending Approval	1
2	VENDOR	ACTIVE	Active	2
3	VENDOR	INACTIVE	Inactive	3
4	VENDOR	BLOCKED	Blocked	4
5	INVOICE	DRAFT	Draft	1
6	INVOICE	OCR_REVIEW_PENDING	Under OCR Review	2
7	INVOICE	OCR_FAILED	OCR Failed	3
8	INVOICE	PENDING_APPROVAL	Pending Approval	4
9	INVOICE	APPROVED	Approved	5
10	INVOICE	REJECTED	Rejected	6
11	INVOICE	PARTIALLY_PAID	Partially Paid	7
12	INVOICE	PAID	Paid	8
13	INVOICE	DISPUTED	Disputed	9
14	PO	OPEN	Open	1
15	PO	CLOSED	Closed	2
16	PO	CANCELLED	Cancelled	3
17	APPROVAL	PENDING	Pending	1
18	APPROVAL	APPROVED	Approved	2
19	APPROVAL	REJECTED	Rejected	3
20	PAYMENT	SCHEDULED	Scheduled	1
21	PAYMENT	SENT	Sent	2
22	PAYMENT	CLEARED	Cleared	3
23	PAYMENT	FAILED	Failed	4
\.


--
-- Data for Name: system_configuration; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.system_configuration (config_key, config_value, data_type, description, updated_by, updated_at) FROM stdin;
AUTO_APPROVAL_LIMIT	5000	NUMBER	Invoices at or below this amount (in base currency) skip manual approval if no other issues are raised	\N	2026-07-22 19:22:11.117003
DUPLICATE_INVOICE_WINDOW_DAYS	90	NUMBER	Lookback window for duplicate invoice_number + vendor_id detection	\N	2026-07-22 19:22:11.117003
PO_MANDATORY	FALSE	BOOLEAN	Whether every invoice must reference a PO	\N	2026-07-22 19:22:11.117003
GRN_MANDATORY	FALSE	BOOLEAN	Whether goods-based invoices require a matching GRN	\N	2026-07-22 19:22:11.117003
PAYMENT_REMINDER_DAYS_BEFORE_DUE	3	NUMBER	Days before due_date to notify AP Executive of an unscheduled invoice	\N	2026-07-22 19:22:11.117003
DEFAULT_BASE_CURRENCY	INR	STRING	Company base currency for reporting and threshold comparisons	\N	2026-07-22 19:22:11.117003
INVOICE_INTAKE_NOTIFICATION_EMAILS	Jagadish.Pannala@pavestechnologies.com	STRING	Email recipients for invoice vendor-not-found and vendor-auto-onboarding notifications	\N	2026-08-11 10:23:04.975024
OCR_CONFIDENCE_THRESHOLD	50	NUMBER	Minimum extraction_confidence (%) before an invoice is auto-promoted; below this, flagged for manual review	\N	2026-07-22 19:22:11.117003
\.


--
-- Data for Name: tax_type; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.tax_type (tax_type_id, country_id, tax_name, tax_code, calculation_type, rate_percent, fixed_amount, is_withholding, effective_from, effective_to, is_system_default, is_active, created_by, created_at, updated_by, updated_at) FROM stdin;
1	1	GST 18%	GST18	PERCENTAGE	18.000	\N	f	2024-01-01	\N	t	t	1	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
2	1	TDS Section 194J	TDS194J	PERCENTAGE	10.000	\N	t	2024-01-01	\N	t	t	1	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
3	3	Standard VAT	VAT-STD	PERCENTAGE	19.000	\N	f	2024-01-01	\N	t	t	1	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
4	2	Sales Tax	SALES-TX	PERCENTAGE	8.250	\N	f	2024-01-01	\N	t	t	1	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
\.


--
-- Data for Name: vendor; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.vendor (vendor_id, vendor_name, vendor_code, country_id, payment_term_id, currency_id, phone_number, email, status_id, created_by, created_at, updated_by, updated_at, pan_number) FROM stdin;
15	AMAZON WEB SERVICES INDIA PRIVATE LIMITED	AWSIPL0336	1	2	1	9100633230	support.aws@example.com	2	5100031	2026-08-10 16:33:37.113797	5100031	2026-08-10 16:33:37.113797	AAJCA9880A
16	KEKA TECHNOLOGIES PRIVATE LIMITED	KTPL1020	1	\N	1	9122541230	admin.keka@keka.com	2	5100031	2026-08-11 13:40:20.883477	5100031	2026-08-11 13:40:20.883477	AAFCK5835K
\.


--
-- Data for Name: vendor_address; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.vendor_address (vendor_address_id, vendor_id, address_type, address_line1, address_line2, city, state, postal_code, country_id, is_primary, created_at, updated_at) FROM stdin;
11	15	REGISTERED	Block E	International Trade Tower, South Delhi	NEHRU PLACE	Delhi	110019	1	t	2026-08-10 16:33:37.822493	2026-08-10 16:33:37.822493
12	16	REGISTERED	Survey no. 17 Vasavi Shalom Sky City	Gachibowli, Rangareddy	Hyderabad	Telangana	500032	1	t	2026-08-11 13:40:21.482888	2026-08-11 13:40:21.482888
\.


--
-- Data for Name: vendor_bank; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.vendor_bank (vendor_bank_id, vendor_id, bank_name, account_holder_name, account_number, iban, swift_code, routing_number, ifsc_code, is_primary, effective_from, effective_to, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: vendor_tax; Type: TABLE DATA; Schema: ap; Owner: avnadmin
--

COPY ap.vendor_tax (vendor_tax_id, registration_type, registration_number, is_verified, verified_at, created_at, vendor_address_id) FROM stdin;
10	GST	07AAJCA9880A1ZL	t	\N	2026-08-10 16:33:38.28736	11
11	GST	36AAFCK5835K1Z6	t	\N	2026-08-11 13:40:21.934612	12
\.


--
-- Name: audit_log_audit_log_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.audit_log_audit_log_id_seq', 70, true);


--
-- Name: country_country_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.country_country_id_seq', 5, true);


--
-- Name: currency_currency_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.currency_currency_id_seq', 3, true);


--
-- Name: goods_receipt_grn_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.goods_receipt_grn_id_seq', 11, true);


--
-- Name: goods_receipt_line_grn_line_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.goods_receipt_line_grn_line_id_seq', 8, true);


--
-- Name: inbound_document_inbound_document_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.inbound_document_inbound_document_id_seq', 22, true);


--
-- Name: invoice_approval_invoice_approval_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.invoice_approval_invoice_approval_id_seq', 1, false);


--
-- Name: invoice_attachment_invoice_attachment_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.invoice_attachment_invoice_attachment_id_seq', 2, true);


--
-- Name: invoice_invoice_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.invoice_invoice_id_seq', 2, true);


--
-- Name: invoice_issue_invoice_issue_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.invoice_issue_invoice_issue_id_seq', 3, true);


--
-- Name: invoice_line_invoice_line_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.invoice_line_invoice_line_id_seq', 2, true);


--
-- Name: payment_invoice_payment_invoice_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.payment_invoice_payment_invoice_id_seq', 1, false);


--
-- Name: payment_payment_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.payment_payment_id_seq', 1, false);


--
-- Name: payment_term_payment_term_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.payment_term_payment_term_id_seq', 5, true);


--
-- Name: purchase_order_line_po_line_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.purchase_order_line_po_line_id_seq', 7, true);


--
-- Name: purchase_order_po_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.purchase_order_po_id_seq', 4, true);


--
-- Name: status_master_status_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.status_master_status_id_seq', 21, true);


--
-- Name: tax_type_tax_type_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.tax_type_tax_type_id_seq', 4, true);


--
-- Name: vendor_address_vendor_address_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.vendor_address_vendor_address_id_seq', 12, true);


--
-- Name: vendor_bank_vendor_bank_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.vendor_bank_vendor_bank_id_seq', 7, true);


--
-- Name: vendor_tax_vendor_tax_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.vendor_tax_vendor_tax_id_seq', 11, true);


--
-- Name: vendor_vendor_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: avnadmin
--

SELECT pg_catalog.setval('ap.vendor_vendor_id_seq', 16, true);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (audit_log_id);


--
-- Name: country country_country_code_key; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.country
    ADD CONSTRAINT country_country_code_key UNIQUE (country_code);


--
-- Name: country country_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.country
    ADD CONSTRAINT country_pkey PRIMARY KEY (country_id);


--
-- Name: currency currency_currency_code_key; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.currency
    ADD CONSTRAINT currency_currency_code_key UNIQUE (currency_code);


--
-- Name: currency currency_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.currency
    ADD CONSTRAINT currency_pkey PRIMARY KEY (currency_id);


--
-- Name: goods_receipt_line goods_receipt_line_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.goods_receipt_line
    ADD CONSTRAINT goods_receipt_line_pkey PRIMARY KEY (grn_line_id);


--
-- Name: goods_receipt goods_receipt_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.goods_receipt
    ADD CONSTRAINT goods_receipt_pkey PRIMARY KEY (grn_id);


--
-- Name: inbound_document inbound_document_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.inbound_document
    ADD CONSTRAINT inbound_document_pkey PRIMARY KEY (inbound_document_id);


--
-- Name: invoice_approval invoice_approval_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_approval
    ADD CONSTRAINT invoice_approval_pkey PRIMARY KEY (invoice_approval_id);


--
-- Name: invoice_attachment invoice_attachment_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_attachment
    ADD CONSTRAINT invoice_attachment_pkey PRIMARY KEY (invoice_attachment_id);


--
-- Name: invoice_issue invoice_issue_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_issue
    ADD CONSTRAINT invoice_issue_pkey PRIMARY KEY (invoice_issue_id);


--
-- Name: invoice_line invoice_line_invoice_id_line_number_key; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_line
    ADD CONSTRAINT invoice_line_invoice_id_line_number_key UNIQUE (invoice_id, line_number);


--
-- Name: invoice_line invoice_line_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_line
    ADD CONSTRAINT invoice_line_pkey PRIMARY KEY (invoice_line_id);


--
-- Name: invoice invoice_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_pkey PRIMARY KEY (invoice_id);


--
-- Name: invoice invoice_vendor_id_invoice_number_key; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_vendor_id_invoice_number_key UNIQUE (vendor_id, invoice_number);


--
-- Name: payment_invoice payment_invoice_payment_id_invoice_id_key; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment_invoice
    ADD CONSTRAINT payment_invoice_payment_id_invoice_id_key UNIQUE (payment_id, invoice_id);


--
-- Name: payment_invoice payment_invoice_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment_invoice
    ADD CONSTRAINT payment_invoice_pkey PRIMARY KEY (payment_invoice_id);


--
-- Name: payment payment_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment
    ADD CONSTRAINT payment_pkey PRIMARY KEY (payment_id);


--
-- Name: payment_term payment_term_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment_term
    ADD CONSTRAINT payment_term_pkey PRIMARY KEY (payment_term_id);


--
-- Name: payment_term payment_term_term_name_key; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment_term
    ADD CONSTRAINT payment_term_term_name_key UNIQUE (term_name);


--
-- Name: purchase_order_line purchase_order_line_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.purchase_order_line
    ADD CONSTRAINT purchase_order_line_pkey PRIMARY KEY (po_line_id);


--
-- Name: purchase_order purchase_order_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.purchase_order
    ADD CONSTRAINT purchase_order_pkey PRIMARY KEY (po_id);


--
-- Name: purchase_order purchase_order_po_number_key; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.purchase_order
    ADD CONSTRAINT purchase_order_po_number_key UNIQUE (po_number);


--
-- Name: status_master status_master_module_name_status_code_key; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.status_master
    ADD CONSTRAINT status_master_module_name_status_code_key UNIQUE (module_name, status_code);


--
-- Name: status_master status_master_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.status_master
    ADD CONSTRAINT status_master_pkey PRIMARY KEY (status_id);


--
-- Name: system_configuration system_configuration_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.system_configuration
    ADD CONSTRAINT system_configuration_pkey PRIMARY KEY (config_key);


--
-- Name: tax_type tax_type_country_id_tax_code_effective_from_key; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.tax_type
    ADD CONSTRAINT tax_type_country_id_tax_code_effective_from_key UNIQUE (country_id, tax_code, effective_from);


--
-- Name: tax_type tax_type_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.tax_type
    ADD CONSTRAINT tax_type_pkey PRIMARY KEY (tax_type_id);


--
-- Name: vendor_address vendor_address_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor_address
    ADD CONSTRAINT vendor_address_pkey PRIMARY KEY (vendor_address_id);


--
-- Name: vendor_bank vendor_bank_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor_bank
    ADD CONSTRAINT vendor_bank_pkey PRIMARY KEY (vendor_bank_id);


--
-- Name: vendor vendor_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_pkey PRIMARY KEY (vendor_id);


--
-- Name: vendor_tax vendor_tax_pkey; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor_tax
    ADD CONSTRAINT vendor_tax_pkey PRIMARY KEY (vendor_tax_id);


--
-- Name: vendor vendor_vendor_code_key; Type: CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_vendor_code_key UNIQUE (vendor_code);


--
-- Name: idx_audit_new_values; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_audit_new_values ON ap.audit_log USING gin (new_values);


--
-- Name: idx_audit_table_record; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_audit_table_record ON ap.audit_log USING btree (table_name, record_id);


--
-- Name: idx_grn_line_grn; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_grn_line_grn ON ap.goods_receipt_line USING btree (grn_id);


--
-- Name: idx_grn_line_po_line; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_grn_line_po_line ON ap.goods_receipt_line USING btree (po_line_id);


--
-- Name: idx_grn_po; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_grn_po ON ap.goods_receipt USING btree (po_id);


--
-- Name: idx_grn_vendor; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_grn_vendor ON ap.goods_receipt USING btree (vendor_id);


--
-- Name: idx_inbound_document_message_id; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_inbound_document_message_id ON ap.inbound_document USING btree (email_message_id);


--
-- Name: idx_inbound_document_raw_data; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_inbound_document_raw_data ON ap.inbound_document USING gin (raw_extracted_data);


--
-- Name: idx_inbound_document_status; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_inbound_document_status ON ap.inbound_document USING btree (extraction_status);


--
-- Name: idx_invoice_approval_invoice; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_invoice_approval_invoice ON ap.invoice_approval USING btree (invoice_id);


--
-- Name: idx_invoice_due_date; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_invoice_due_date ON ap.invoice USING btree (due_date);


--
-- Name: idx_invoice_issue_invoice; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_invoice_issue_invoice ON ap.invoice_issue USING btree (invoice_id);


--
-- Name: idx_invoice_issue_severity; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_invoice_issue_severity ON ap.invoice_issue USING btree (severity);


--
-- Name: idx_invoice_po; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_invoice_po ON ap.invoice USING btree (po_id);


--
-- Name: idx_invoice_status; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_invoice_status ON ap.invoice USING btree (status_id);


--
-- Name: idx_invoice_vendor; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_invoice_vendor ON ap.invoice USING btree (vendor_id);


--
-- Name: idx_payment_invoice_invoice; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_payment_invoice_invoice ON ap.payment_invoice USING btree (invoice_id);


--
-- Name: idx_payment_invoice_payment; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_payment_invoice_payment ON ap.payment_invoice USING btree (payment_id);


--
-- Name: idx_payment_scheduled_date; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_payment_scheduled_date ON ap.payment USING btree (scheduled_date);


--
-- Name: idx_payment_vendor; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_payment_vendor ON ap.payment USING btree (vendor_id);


--
-- Name: idx_po_line_po; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_po_line_po ON ap.purchase_order_line USING btree (po_id);


--
-- Name: idx_po_vendor; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_po_vendor ON ap.purchase_order USING btree (vendor_id);


--
-- Name: idx_vendor_address_vendor; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_vendor_address_vendor ON ap.vendor_address USING btree (vendor_id);


--
-- Name: idx_vendor_bank_active; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_vendor_bank_active ON ap.vendor_bank USING btree (vendor_id, effective_to);


--
-- Name: idx_vendor_bank_vendor; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_vendor_bank_vendor ON ap.vendor_bank USING btree (vendor_id);


--
-- Name: idx_vendor_country; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_vendor_country ON ap.vendor USING btree (country_id);


--
-- Name: idx_vendor_email; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_vendor_email ON ap.vendor USING btree (email);


--
-- Name: idx_vendor_status; Type: INDEX; Schema: ap; Owner: avnadmin
--

CREATE INDEX idx_vendor_status ON ap.vendor USING btree (status_id);


--
-- Name: inbound_document fk_inbound_document_invoice; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.inbound_document
    ADD CONSTRAINT fk_inbound_document_invoice FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id);


--
-- Name: goods_receipt_line goods_receipt_line_grn_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.goods_receipt_line
    ADD CONSTRAINT goods_receipt_line_grn_id_fkey FOREIGN KEY (grn_id) REFERENCES ap.goods_receipt(grn_id) ON DELETE CASCADE;


--
-- Name: goods_receipt_line goods_receipt_line_po_line_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.goods_receipt_line
    ADD CONSTRAINT goods_receipt_line_po_line_id_fkey FOREIGN KEY (po_line_id) REFERENCES ap.purchase_order_line(po_line_id) ON DELETE SET NULL;


--
-- Name: goods_receipt goods_receipt_po_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.goods_receipt
    ADD CONSTRAINT goods_receipt_po_id_fkey FOREIGN KEY (po_id) REFERENCES ap.purchase_order(po_id);


--
-- Name: goods_receipt goods_receipt_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.goods_receipt
    ADD CONSTRAINT goods_receipt_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: inbound_document inbound_document_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.inbound_document
    ADD CONSTRAINT inbound_document_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: invoice_approval invoice_approval_invoice_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_approval
    ADD CONSTRAINT invoice_approval_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id) ON DELETE CASCADE;


--
-- Name: invoice_approval invoice_approval_invoice_issue_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_approval
    ADD CONSTRAINT invoice_approval_invoice_issue_id_fkey FOREIGN KEY (invoice_issue_id) REFERENCES ap.invoice_issue(invoice_issue_id);


--
-- Name: invoice_attachment invoice_attachment_invoice_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_attachment
    ADD CONSTRAINT invoice_attachment_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id) ON DELETE CASCADE;


--
-- Name: invoice invoice_currency_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES ap.currency(currency_id);


--
-- Name: invoice invoice_grn_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_grn_id_fkey FOREIGN KEY (grn_id) REFERENCES ap.goods_receipt(grn_id);


--
-- Name: invoice invoice_inbound_document_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_inbound_document_id_fkey FOREIGN KEY (inbound_document_id) REFERENCES ap.inbound_document(inbound_document_id);


--
-- Name: invoice_issue invoice_issue_invoice_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_issue
    ADD CONSTRAINT invoice_issue_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id) ON DELETE CASCADE;


--
-- Name: invoice_issue invoice_issue_status_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_issue
    ADD CONSTRAINT invoice_issue_status_id_fkey FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: invoice_line invoice_line_invoice_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_line
    ADD CONSTRAINT invoice_line_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id) ON DELETE CASCADE;


--
-- Name: invoice_line invoice_line_tax_type_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice_line
    ADD CONSTRAINT invoice_line_tax_type_id_fkey FOREIGN KEY (tax_type_id) REFERENCES ap.tax_type(tax_type_id);


--
-- Name: invoice invoice_payment_term_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_payment_term_id_fkey FOREIGN KEY (payment_term_id) REFERENCES ap.payment_term(payment_term_id);


--
-- Name: invoice invoice_po_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_po_id_fkey FOREIGN KEY (po_id) REFERENCES ap.purchase_order(po_id);


--
-- Name: invoice invoice_status_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_status_id_fkey FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: invoice invoice_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: payment payment_currency_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment
    ADD CONSTRAINT payment_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES ap.currency(currency_id);


--
-- Name: payment_invoice payment_invoice_invoice_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment_invoice
    ADD CONSTRAINT payment_invoice_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id);


--
-- Name: payment_invoice payment_invoice_payment_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment_invoice
    ADD CONSTRAINT payment_invoice_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES ap.payment(payment_id) ON DELETE CASCADE;


--
-- Name: payment payment_status_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment
    ADD CONSTRAINT payment_status_id_fkey FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: payment payment_vendor_bank_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment
    ADD CONSTRAINT payment_vendor_bank_id_fkey FOREIGN KEY (vendor_bank_id) REFERENCES ap.vendor_bank(vendor_bank_id);


--
-- Name: payment payment_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.payment
    ADD CONSTRAINT payment_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: purchase_order purchase_order_currency_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.purchase_order
    ADD CONSTRAINT purchase_order_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES ap.currency(currency_id);


--
-- Name: purchase_order_line purchase_order_line_po_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.purchase_order_line
    ADD CONSTRAINT purchase_order_line_po_id_fkey FOREIGN KEY (po_id) REFERENCES ap.purchase_order(po_id) ON DELETE CASCADE;


--
-- Name: purchase_order purchase_order_status_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.purchase_order
    ADD CONSTRAINT purchase_order_status_id_fkey FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: purchase_order purchase_order_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.purchase_order
    ADD CONSTRAINT purchase_order_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: tax_type tax_type_country_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.tax_type
    ADD CONSTRAINT tax_type_country_id_fkey FOREIGN KEY (country_id) REFERENCES ap.country(country_id);


--
-- Name: vendor_address vendor_address_country_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor_address
    ADD CONSTRAINT vendor_address_country_id_fkey FOREIGN KEY (country_id) REFERENCES ap.country(country_id);


--
-- Name: vendor_address vendor_address_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor_address
    ADD CONSTRAINT vendor_address_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id) ON DELETE CASCADE;


--
-- Name: vendor_bank vendor_bank_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor_bank
    ADD CONSTRAINT vendor_bank_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id) ON DELETE CASCADE;


--
-- Name: vendor vendor_country_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_country_id_fkey FOREIGN KEY (country_id) REFERENCES ap.country(country_id);


--
-- Name: vendor vendor_currency_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES ap.currency(currency_id);


--
-- Name: vendor vendor_payment_term_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_payment_term_id_fkey FOREIGN KEY (payment_term_id) REFERENCES ap.payment_term(payment_term_id);


--
-- Name: vendor vendor_status_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_status_id_fkey FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: vendor_tax vendor_tax_vendor_address_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: avnadmin
--

ALTER TABLE ONLY ap.vendor_tax
    ADD CONSTRAINT vendor_tax_vendor_address_id_fkey FOREIGN KEY (vendor_address_id) REFERENCES ap.vendor_address(vendor_address_id);


--
-- PostgreSQL database dump complete
--

\unrestrict v1DXah13nnkz76uPAQztmBznmGgircHZcqaUQ4mpaGlUBkmAh2RTEyb6eANFkUN

