--
-- PostgreSQL database dump
--

\restrict ROJpVzdXNx6uIrfufmS11Ovye9cVWYZR8YMw74pBVJtl0SFspn00osLriFtMC39

-- Dumped from database version 17.11
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
-- Name: ap; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA ap;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: audit_log; Type: TABLE; Schema: ap; Owner: -
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


--
-- Name: audit_log_audit_log_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.audit_log_audit_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_log_audit_log_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.audit_log_audit_log_id_seq OWNED BY ap.audit_log.audit_log_id;


--
-- Name: country; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.country (
    country_id integer NOT NULL,
    country_name character varying(100) NOT NULL,
    country_code character(2) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: country_country_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.country_country_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: country_country_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.country_country_id_seq OWNED BY ap.country.country_id;


--
-- Name: currency; Type: TABLE; Schema: ap; Owner: -
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


--
-- Name: currency_currency_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.currency_currency_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: currency_currency_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.currency_currency_id_seq OWNED BY ap.currency.currency_id;


--
-- Name: department; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.department (
    id bigint NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(150) NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: department_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.department_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: department_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.department_id_seq OWNED BY ap.department.id;


--
-- Name: department_purchase_category; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.department_purchase_category (
    department_id bigint NOT NULL,
    purchase_category_id bigint NOT NULL
);


--
-- Name: goods_receipt; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.goods_receipt (
    grn_id integer NOT NULL,
    po_id bigint,
    vendor_id integer NOT NULL,
    file_path character varying(500),
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    grn_number character varying(50),
    receipt_date date
);


--
-- Name: goods_receipt_grn_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.goods_receipt_grn_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: goods_receipt_grn_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.goods_receipt_grn_id_seq OWNED BY ap.goods_receipt.grn_id;


--
-- Name: goods_receipt_line; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.goods_receipt_line (
    grn_line_id integer NOT NULL,
    grn_id integer NOT NULL,
    description character varying(255) NOT NULL,
    received_quantity numeric(18,4) NOT NULL,
    po_line_id integer,
    item_code character varying(50)
);


--
-- Name: goods_receipt_line_grn_line_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.goods_receipt_line_grn_line_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: goods_receipt_line_grn_line_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.goods_receipt_line_grn_line_id_seq OWNED BY ap.goods_receipt_line.grn_line_id;


--
-- Name: inbound_document; Type: TABLE; Schema: ap; Owner: -
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


--
-- Name: inbound_document_inbound_document_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.inbound_document_inbound_document_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: inbound_document_inbound_document_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.inbound_document_inbound_document_id_seq OWNED BY ap.inbound_document.inbound_document_id;


--
-- Name: invoice; Type: TABLE; Schema: ap; Owner: -
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


--
-- Name: invoice_approval; Type: TABLE; Schema: ap; Owner: -
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


--
-- Name: invoice_approval_invoice_approval_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.invoice_approval_invoice_approval_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: invoice_approval_invoice_approval_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.invoice_approval_invoice_approval_id_seq OWNED BY ap.invoice_approval.invoice_approval_id;


--
-- Name: invoice_attachment; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.invoice_attachment (
    invoice_attachment_id integer NOT NULL,
    invoice_id integer NOT NULL,
    file_name character varying(255) NOT NULL,
    file_path character varying(500) NOT NULL,
    uploaded_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: invoice_attachment_invoice_attachment_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.invoice_attachment_invoice_attachment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: invoice_attachment_invoice_attachment_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.invoice_attachment_invoice_attachment_id_seq OWNED BY ap.invoice_attachment.invoice_attachment_id;


--
-- Name: invoice_invoice_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.invoice_invoice_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: invoice_invoice_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.invoice_invoice_id_seq OWNED BY ap.invoice.invoice_id;


--
-- Name: invoice_issue; Type: TABLE; Schema: ap; Owner: -
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


--
-- Name: invoice_issue_invoice_issue_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.invoice_issue_invoice_issue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: invoice_issue_invoice_issue_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.invoice_issue_invoice_issue_id_seq OWNED BY ap.invoice_issue.invoice_issue_id;


--
-- Name: invoice_line; Type: TABLE; Schema: ap; Owner: -
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
    tax_amount numeric(18,2) DEFAULT 0 NOT NULL,
    po_line_id integer
);


--
-- Name: invoice_line_invoice_line_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.invoice_line_invoice_line_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: invoice_line_invoice_line_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.invoice_line_invoice_line_id_seq OWNED BY ap.invoice_line.invoice_line_id;


--
-- Name: payment; Type: TABLE; Schema: ap; Owner: -
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


--
-- Name: payment_invoice; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.payment_invoice (
    payment_invoice_id integer NOT NULL,
    payment_id integer NOT NULL,
    invoice_id integer NOT NULL,
    allocated_amount numeric(18,2) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: payment_invoice_payment_invoice_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.payment_invoice_payment_invoice_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: payment_invoice_payment_invoice_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.payment_invoice_payment_invoice_id_seq OWNED BY ap.payment_invoice.payment_invoice_id;


--
-- Name: payment_payment_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.payment_payment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: payment_payment_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.payment_payment_id_seq OWNED BY ap.payment.payment_id;


--
-- Name: payment_term; Type: TABLE; Schema: ap; Owner: -
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


--
-- Name: payment_term_payment_term_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.payment_term_payment_term_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: payment_term_payment_term_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.payment_term_payment_term_id_seq OWNED BY ap.payment_term.payment_term_id;


--
-- Name: purchase_category; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.purchase_category (
    id bigint NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(150) NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: purchase_category_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.purchase_category_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: purchase_category_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.purchase_category_id_seq OWNED BY ap.purchase_category.id;


--
-- Name: purchase_order; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.purchase_order (
    id bigint NOT NULL,
    po_number character varying(50) NOT NULL,
    pr_id bigint NOT NULL,
    quotation_id bigint,
    vendor_id bigint NOT NULL,
    po_date date DEFAULT CURRENT_DATE NOT NULL,
    expected_delivery_date date,
    delivery_location character varying(255),
    payment_terms text,
    delivery_terms text,
    subtotal numeric(18,2) DEFAULT 0 NOT NULL,
    tax_amount numeric(18,2) DEFAULT 0 NOT NULL,
    total_amount numeric(18,2) DEFAULT 0 NOT NULL,
    status_id bigint NOT NULL,
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_po_subtotal CHECK ((subtotal >= (0)::numeric)),
    CONSTRAINT chk_po_tax CHECK ((tax_amount >= (0)::numeric)),
    CONSTRAINT chk_po_total CHECK ((total_amount >= (0)::numeric))
);


--
-- Name: purchase_order_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.purchase_order_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: purchase_order_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.purchase_order_id_seq OWNED BY ap.purchase_order.id;


--
-- Name: purchase_order_line; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.purchase_order_line (
    id bigint NOT NULL,
    po_id bigint NOT NULL,
    pr_line_id bigint,
    item_name character varying(255) NOT NULL,
    description text,
    quantity numeric(18,4) NOT NULL,
    uom character varying(50),
    unit_price numeric(18,2) DEFAULT 0 NOT NULL,
    tax_rate numeric(8,4) DEFAULT 0 NOT NULL,
    tax_amount numeric(18,2) DEFAULT 0 NOT NULL,
    total_amount numeric(18,2) DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_po_line_quantity CHECK ((quantity > (0)::numeric)),
    CONSTRAINT chk_po_line_tax_amount CHECK ((tax_amount >= (0)::numeric)),
    CONSTRAINT chk_po_line_tax_rate CHECK ((tax_rate >= (0)::numeric)),
    CONSTRAINT chk_po_line_total CHECK ((total_amount >= (0)::numeric)),
    CONSTRAINT chk_po_line_unit_price CHECK ((unit_price >= (0)::numeric))
);


--
-- Name: purchase_order_line_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.purchase_order_line_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: purchase_order_line_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.purchase_order_line_id_seq OWNED BY ap.purchase_order_line.id;


--
-- Name: purchase_requisition; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.purchase_requisition (
    id bigint NOT NULL,
    pr_number character varying(50) NOT NULL,
    department_id bigint NOT NULL,
    purchase_category_id bigint NOT NULL,
    status_id bigint NOT NULL,
    priority character varying(20) DEFAULT 'NORMAL'::character varying NOT NULL,
    required_by date,
    delivery_location character varying(255),
    justification text,
    estimated_total numeric(18,2) DEFAULT 0 NOT NULL,
    selected_vendor_id bigint,
    selected_quotation_id bigint,
    approved_by character varying(100),
    approved_at timestamp with time zone,
    approval_comment text,
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_pr_estimated_total CHECK ((estimated_total >= (0)::numeric)),
    CONSTRAINT chk_pr_priority CHECK (((priority)::text = ANY ((ARRAY['LOW'::character varying, 'NORMAL'::character varying, 'HIGH'::character varying, 'URGENT'::character varying])::text[])))
);


--
-- Name: purchase_requisition_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.purchase_requisition_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: purchase_requisition_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.purchase_requisition_id_seq OWNED BY ap.purchase_requisition.id;


--
-- Name: purchase_requisition_line; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.purchase_requisition_line (
    id bigint NOT NULL,
    pr_id bigint NOT NULL,
    item_name character varying(255) NOT NULL,
    description text,
    quantity numeric(18,4) NOT NULL,
    uom character varying(50),
    estimated_unit_price numeric(18,2),
    estimated_amount numeric(18,2),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_pr_line_estimated_amount CHECK (((estimated_amount IS NULL) OR (estimated_amount >= (0)::numeric))),
    CONSTRAINT chk_pr_line_estimated_price CHECK (((estimated_unit_price IS NULL) OR (estimated_unit_price >= (0)::numeric))),
    CONSTRAINT chk_pr_line_quantity CHECK ((quantity > (0)::numeric))
);


--
-- Name: purchase_requisition_line_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.purchase_requisition_line_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: purchase_requisition_line_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.purchase_requisition_line_id_seq OWNED BY ap.purchase_requisition_line.id;


--
-- Name: quotation; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.quotation (
    id bigint NOT NULL,
    quotation_number character varying(100),
    pr_id bigint NOT NULL,
    vendor_id bigint NOT NULL,
    quotation_date date,
    valid_until date,
    total_amount numeric(18,2),
    file_url text NOT NULL,
    status_id bigint NOT NULL,
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_quotation_total CHECK (((total_amount IS NULL) OR (total_amount >= (0)::numeric)))
);


--
-- Name: quotation_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.quotation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: quotation_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.quotation_id_seq OWNED BY ap.quotation.id;


--
-- Name: status_master; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.status_master (
    status_id integer NOT NULL,
    module_name character varying(50) NOT NULL,
    status_code character varying(30) NOT NULL,
    status_name character varying(100) NOT NULL,
    display_order smallint DEFAULT 0 NOT NULL
);


--
-- Name: status_master_status_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.status_master_status_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: status_master_status_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.status_master_status_id_seq OWNED BY ap.status_master.status_id;


--
-- Name: system_configuration; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.system_configuration (
    config_key character varying(100) NOT NULL,
    config_value character varying(255) NOT NULL,
    data_type character varying(20) DEFAULT 'STRING'::character varying NOT NULL,
    description character varying(255),
    updated_by character varying(100),
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: tax_rate_rule; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.tax_rate_rule (
    tax_rate_rule_id integer NOT NULL,
    tax_rule_id integer NOT NULL,
    rate_percent numeric(7,4) NOT NULL,
    calculation_type character varying(30) DEFAULT 'PERCENTAGE'::character varying NOT NULL,
    fixed_amount numeric(18,2),
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by character varying(100),
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT tax_rate_effective_dates_chk CHECK (((effective_to IS NULL) OR (effective_to >= effective_from))),
    CONSTRAINT tax_rate_non_negative_chk CHECK ((rate_percent >= (0)::numeric))
);


--
-- Name: tax_rate_rule_tax_rate_rule_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.tax_rate_rule_tax_rate_rule_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tax_rate_rule_tax_rate_rule_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.tax_rate_rule_tax_rate_rule_id_seq OWNED BY ap.tax_rate_rule.tax_rate_rule_id;


--
-- Name: tax_rule; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.tax_rule (
    tax_rule_id integer NOT NULL,
    rule_code character varying(100) NOT NULL,
    rule_name character varying(255) NOT NULL,
    tax_type_id integer NOT NULL,
    rule_category character varying(50) NOT NULL,
    description text,
    priority integer DEFAULT 100 NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by character varying(100),
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT tax_rule_effective_dates_chk CHECK (((effective_to IS NULL) OR (effective_to >= effective_from)))
);


--
-- Name: tax_rule_condition; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.tax_rule_condition (
    tax_rule_condition_id integer NOT NULL,
    tax_rule_id integer NOT NULL,
    condition_type character varying(50) NOT NULL,
    operator character varying(20) NOT NULL,
    condition_value character varying(500) NOT NULL,
    logical_group integer DEFAULT 1 NOT NULL,
    sequence_no integer DEFAULT 1 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: tax_rule_condition_tax_rule_condition_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.tax_rule_condition_tax_rule_condition_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tax_rule_condition_tax_rule_condition_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.tax_rule_condition_tax_rule_condition_id_seq OWNED BY ap.tax_rule_condition.tax_rule_condition_id;


--
-- Name: tax_rule_tax_rule_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.tax_rule_tax_rule_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tax_rule_tax_rule_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.tax_rule_tax_rule_id_seq OWNED BY ap.tax_rule.tax_rule_id;


--
-- Name: tax_type; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.tax_type (
    tax_type_id integer NOT NULL,
    country_id integer NOT NULL,
    tax_name character varying(100) NOT NULL,
    tax_code character varying(30) NOT NULL,
    is_withholding boolean DEFAULT false NOT NULL,
    is_system_default boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_by character varying(100),
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: tax_type_tax_type_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.tax_type_tax_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tax_type_tax_type_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.tax_type_tax_type_id_seq OWNED BY ap.tax_type.tax_type_id;


--
-- Name: vendor; Type: TABLE; Schema: ap; Owner: -
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


--
-- Name: vendor_address; Type: TABLE; Schema: ap; Owner: -
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


--
-- Name: vendor_address_vendor_address_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.vendor_address_vendor_address_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: vendor_address_vendor_address_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.vendor_address_vendor_address_id_seq OWNED BY ap.vendor_address.vendor_address_id;


--
-- Name: vendor_bank; Type: TABLE; Schema: ap; Owner: -
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


--
-- Name: vendor_bank_vendor_bank_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.vendor_bank_vendor_bank_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: vendor_bank_vendor_bank_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.vendor_bank_vendor_bank_id_seq OWNED BY ap.vendor_bank.vendor_bank_id;


--
-- Name: vendor_category; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.vendor_category (
    vendor_category_id integer NOT NULL,
    category_code character varying(50) NOT NULL,
    category_name character varying(150) NOT NULL,
    parent_category_id integer,
    description character varying(500),
    is_active boolean DEFAULT true NOT NULL,
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_by character varying(100),
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: vendor_category_mapping; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.vendor_category_mapping (
    vendor_category_mapping_id integer NOT NULL,
    vendor_id integer NOT NULL,
    vendor_category_id integer NOT NULL,
    is_primary boolean DEFAULT false NOT NULL,
    created_by character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_by character varying(100),
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: vendor_category_mapping_vendor_category_mapping_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

ALTER TABLE ap.vendor_category_mapping ALTER COLUMN vendor_category_mapping_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME ap.vendor_category_mapping_vendor_category_mapping_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: vendor_category_vendor_category_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

ALTER TABLE ap.vendor_category ALTER COLUMN vendor_category_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME ap.vendor_category_vendor_category_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: vendor_tax; Type: TABLE; Schema: ap; Owner: -
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


--
-- Name: vendor_tax_vendor_tax_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.vendor_tax_vendor_tax_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: vendor_tax_vendor_tax_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.vendor_tax_vendor_tax_id_seq OWNED BY ap.vendor_tax.vendor_tax_id;


--
-- Name: vendor_vendor_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.vendor_vendor_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: vendor_vendor_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.vendor_vendor_id_seq OWNED BY ap.vendor.vendor_id;


--
-- Name: audit_log audit_log_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.audit_log ALTER COLUMN audit_log_id SET DEFAULT nextval('ap.audit_log_audit_log_id_seq'::regclass);


--
-- Name: country country_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.country ALTER COLUMN country_id SET DEFAULT nextval('ap.country_country_id_seq'::regclass);


--
-- Name: currency currency_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.currency ALTER COLUMN currency_id SET DEFAULT nextval('ap.currency_currency_id_seq'::regclass);


--
-- Name: department id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.department ALTER COLUMN id SET DEFAULT nextval('ap.department_id_seq'::regclass);


--
-- Name: goods_receipt grn_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.goods_receipt ALTER COLUMN grn_id SET DEFAULT nextval('ap.goods_receipt_grn_id_seq'::regclass);


--
-- Name: goods_receipt_line grn_line_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.goods_receipt_line ALTER COLUMN grn_line_id SET DEFAULT nextval('ap.goods_receipt_line_grn_line_id_seq'::regclass);


--
-- Name: inbound_document inbound_document_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.inbound_document ALTER COLUMN inbound_document_id SET DEFAULT nextval('ap.inbound_document_inbound_document_id_seq'::regclass);


--
-- Name: invoice invoice_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice ALTER COLUMN invoice_id SET DEFAULT nextval('ap.invoice_invoice_id_seq'::regclass);


--
-- Name: invoice_approval invoice_approval_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval ALTER COLUMN invoice_approval_id SET DEFAULT nextval('ap.invoice_approval_invoice_approval_id_seq'::regclass);


--
-- Name: invoice_attachment invoice_attachment_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_attachment ALTER COLUMN invoice_attachment_id SET DEFAULT nextval('ap.invoice_attachment_invoice_attachment_id_seq'::regclass);


--
-- Name: invoice_issue invoice_issue_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_issue ALTER COLUMN invoice_issue_id SET DEFAULT nextval('ap.invoice_issue_invoice_issue_id_seq'::regclass);


--
-- Name: invoice_line invoice_line_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_line ALTER COLUMN invoice_line_id SET DEFAULT nextval('ap.invoice_line_invoice_line_id_seq'::regclass);


--
-- Name: payment payment_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment ALTER COLUMN payment_id SET DEFAULT nextval('ap.payment_payment_id_seq'::regclass);


--
-- Name: payment_invoice payment_invoice_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment_invoice ALTER COLUMN payment_invoice_id SET DEFAULT nextval('ap.payment_invoice_payment_invoice_id_seq'::regclass);


--
-- Name: payment_term payment_term_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment_term ALTER COLUMN payment_term_id SET DEFAULT nextval('ap.payment_term_payment_term_id_seq'::regclass);


--
-- Name: purchase_category id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_category ALTER COLUMN id SET DEFAULT nextval('ap.purchase_category_id_seq'::regclass);


--
-- Name: purchase_order id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_order ALTER COLUMN id SET DEFAULT nextval('ap.purchase_order_id_seq'::regclass);


--
-- Name: purchase_order_line id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_order_line ALTER COLUMN id SET DEFAULT nextval('ap.purchase_order_line_id_seq'::regclass);


--
-- Name: purchase_requisition id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_requisition ALTER COLUMN id SET DEFAULT nextval('ap.purchase_requisition_id_seq'::regclass);


--
-- Name: purchase_requisition_line id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_requisition_line ALTER COLUMN id SET DEFAULT nextval('ap.purchase_requisition_line_id_seq'::regclass);


--
-- Name: quotation id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.quotation ALTER COLUMN id SET DEFAULT nextval('ap.quotation_id_seq'::regclass);


--
-- Name: status_master status_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.status_master ALTER COLUMN status_id SET DEFAULT nextval('ap.status_master_status_id_seq'::regclass);


--
-- Name: tax_rate_rule tax_rate_rule_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_rate_rule ALTER COLUMN tax_rate_rule_id SET DEFAULT nextval('ap.tax_rate_rule_tax_rate_rule_id_seq'::regclass);


--
-- Name: tax_rule tax_rule_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_rule ALTER COLUMN tax_rule_id SET DEFAULT nextval('ap.tax_rule_tax_rule_id_seq'::regclass);


--
-- Name: tax_rule_condition tax_rule_condition_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_rule_condition ALTER COLUMN tax_rule_condition_id SET DEFAULT nextval('ap.tax_rule_condition_tax_rule_condition_id_seq'::regclass);


--
-- Name: tax_type tax_type_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_type ALTER COLUMN tax_type_id SET DEFAULT nextval('ap.tax_type_tax_type_id_seq'::regclass);


--
-- Name: vendor vendor_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor ALTER COLUMN vendor_id SET DEFAULT nextval('ap.vendor_vendor_id_seq'::regclass);


--
-- Name: vendor_address vendor_address_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_address ALTER COLUMN vendor_address_id SET DEFAULT nextval('ap.vendor_address_vendor_address_id_seq'::regclass);


--
-- Name: vendor_bank vendor_bank_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_bank ALTER COLUMN vendor_bank_id SET DEFAULT nextval('ap.vendor_bank_vendor_bank_id_seq'::regclass);


--
-- Name: vendor_tax vendor_tax_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_tax ALTER COLUMN vendor_tax_id SET DEFAULT nextval('ap.vendor_tax_vendor_tax_id_seq'::regclass);


--
-- Data for Name: audit_log; Type: TABLE DATA; Schema: ap; Owner: -
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
71	invoice	3	STATUS_UPDATE	1	2026-08-18 09:22:06.363255	\N	{"status_code": "PENDING_APPROVAL"}
72	invoice	3	STATUS_UPDATE	1	2026-08-18 09:23:15.62463	\N	{"status_code": "PENDING_APPROVAL"}
73	invoice	3	STATUS_UPDATE	1	2026-08-18 09:24:37.196291	\N	{"status_code": "PENDING_APPROVAL"}
74	invoice	3	STATUS_UPDATE	1	2026-08-18 09:25:22.141364	\N	{"status_code": "PENDING_APPROVAL"}
75	invoice	3	APPROVE	1	2026-08-18 09:26:12.575913	\N	{"comments": "approved", "status_code": "APPROVED"}
76	invoice	3	STATUS_UPDATE	1	2026-08-18 09:31:13.64011	\N	{"status_code": "PENDING_APPROVAL"}
77	invoice	3	STATUS_UPDATE	1	2026-08-18 09:32:17.670387	\N	{"status_code": "APPROVED"}
78	invoice	3	STATUS_UPDATE	1	2026-08-18 09:43:44.483009	\N	{"status_code": "PENDING_APPROVAL"}
79	invoice	3	STATUS_UPDATE	1	2026-08-18 09:44:35.833562	\N	{"status_code": "APPROVED"}
80	invoice	3	STATUS_UPDATE	1	2026-08-18 09:50:29.663338	\N	{"status_code": "PENDING_APPROVAL"}
81	invoice	3	STATUS_UPDATE	1	2026-08-18 09:51:21.058496	\N	{"status_code": "APPROVED"}
82	invoice	3	STATUS_UPDATE	1	2026-08-18 09:52:46.088858	\N	{"status_code": "PENDING_APPROVAL"}
83	invoice	3	STATUS_UPDATE	1	2026-08-18 09:53:07.271624	\N	{"status_code": "APPROVED"}
84	invoice	3	STATUS_UPDATE	1	2026-08-18 09:53:42.404764	\N	{"status_code": "APPROVED"}
85	invoice	3	STATUS_UPDATE	1	2026-08-18 09:56:18.184724	\N	{"status_code": "OCR_REVIEW_PENDING"}
86	invoice	3	STATUS_UPDATE	1	2026-08-18 10:22:55.655903	\N	{"status_code": "OCR_REVIEW_PENDING"}
87	invoice	3	STATUS_UPDATE	1	2026-08-18 10:24:07.374077	\N	{"status_code": "OCR_REVIEW_PENDING"}
88	invoice	3	STATUS_UPDATE	1	2026-08-18 10:27:56.255871	\N	{"status_code": "OCR_REVIEW_PENDING"}
89	invoice	3	STATUS_UPDATE	1	2026-08-18 10:30:51.668322	\N	{"status_code": "PENDING_APPROVAL"}
90	invoice	3	STATUS_UPDATE	1	2026-08-18 10:31:06.855153	\N	{"status_code": "APPROVED"}
91	invoice	11	STATUS_UPDATE	1	2026-08-24 11:43:37.555643	\N	{"status_code": "PENDING_APPROVAL"}
92	invoice	12	STATUS_UPDATE	1	2026-08-24 11:55:08.116638	\N	{"status_code": "PENDING_APPROVAL"}
93	purchase_order	5	CREATE	1	2026-08-27 12:40:28.315613	null	{"po_date": "2025-05-12", "subtotal": "3055.7200000000003", "file_path": null, "po_number": "PO-AWS-2026-00125", "status_id": 14, "vendor_id": 15, "tax_amount": "550.03", "currency_id": 1, "total_amount": "3605.75", "expected_delivery_date": "2026-06-01"}
94	goods_receipt	12	CREATE	1	2026-08-28 07:42:02.069147	null	{"po_id": 5, "file_path": null, "vendor_id": 15, "grn_number": "GRN-AWS-2026-00125", "receipt_date": "2026-02-06"}
95	purchase_order	5	UPDATE	1	2026-08-28 07:46:27.135603	{"file_path": null}	{"file_path": "invoices/2026/08/24b0270d77544909a384cf32b4eece0a_PO_AWS_Matched_to_Original_Invoice.pdf"}
96	goods_receipt	12	UPDATE	1	2026-08-28 07:46:42.165545	{"file_path": null}	{"file_path": "invoices/2026/08/1877139e0cd645d8a9e60c2697d6477f_GRN_AWS_Matched_to_Original_Invoice.pdf"}
\.


--
-- Data for Name: country; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.country (country_id, country_name, country_code, is_active, created_at) FROM stdin;
1	India	IN	t	2026-07-22 19:22:11.117003
2	United States	US	f	2026-07-22 19:22:11.117003
3	Germany	DE	f	2026-07-22 19:22:11.117003
4	United Arab Emirates	AE	f	2026-07-22 19:22:11.117003
5	Singapore	SG	f	2026-07-22 19:22:11.117003
6	Brazil	BR	t	2026-08-18 06:53:37.000222
\.


--
-- Data for Name: currency; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.currency (currency_id, currency_name, currency_code, symbol, decimal_places, is_active, created_at) FROM stdin;
1	Indian Rupee	INR	₹	2	t	2026-07-22 19:22:11.117003
2	US Dollar	USD	$	2	t	2026-07-22 19:22:11.117003
3	Euro	EUR	€	2	t	2026-07-22 19:22:11.117003
\.


--
-- Data for Name: department; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.department (id, code, name, description, is_active, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: department_purchase_category; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.department_purchase_category (department_id, purchase_category_id) FROM stdin;
\.


--
-- Data for Name: goods_receipt; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.goods_receipt (grn_id, po_id, vendor_id, file_path, created_by, created_at, grn_number, receipt_date) FROM stdin;
\.


--
-- Data for Name: goods_receipt_line; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.goods_receipt_line (grn_line_id, grn_id, description, received_quantity, po_line_id, item_code) FROM stdin;
\.


--
-- Data for Name: inbound_document; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.inbound_document (inbound_document_id, source_type, email_from, email_subject, email_message_id, received_at, file_name, file_path, extraction_status, extraction_confidence, raw_extracted_data, vendor_id, invoice_id, created_at) FROM stdin;
1	UPLOAD	\N	\N	\N	2026-08-10 16:18:47.006694	aws-gst-invoice-may-2026.pdf	invoices/2026/08/0a97685cdd834c97887258139bb77b9f_aws-gst-invoice-may-2026.pdf	FAILED	\N	\N	\N	\N	2026-08-10 16:18:47.006694
27	UPLOAD	\N	\N	\N	2026-08-20 12:24:07.991985	system_generated_sample_invoice_gstin_9924USA29003OSI.pdf	invoices/2026/08/141b4a294eb448d899a9f824571c009a_system_generated_sample_invoice_gstin_9924USA29003OSI.pdf	REVIEW_REQUIRED	\N	{"tax": {"tax_type": "INTRA_STATE_CGST_SGST", "cess_rate": null, "cgst_rate": 9.0, "igst_rate": null, "sgst_rate": 9.0, "ugst_rate": null, "reverse_charge": false, "place_of_supply": "Telangana"}, "buyer": {"pan": "AABCA1234F", "name": "Apex Business Solutions Private Limited", "email": null, "gstin": "36AABCA1234F1Z5", "phone": null, "state": "Telangana", "address": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\nHyderabad, Telangana 500081\\n-\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36", "country": null, "legal_name": "Apex Business Solutions Private Limited", "state_code": "36", "trade_name": null, "shipping_address": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\n-\\nHyderabad, Telangana 500081\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36"}, "vendor": {"pan": null, "name": "Global Software Solutions Pvt. Ltd.", "email": null, "gstin": "9924USA29003OSI", "phone": null, "state": null, "address": "Global Software Solutions Pvt. Ltd.\\n5th Floor, Tech Park, Hitech City\\nHyderabad, Telangana 500081\\n-", "country": null, "website": null, "legal_name": "Global Software Solutions Pvt. Ltd.", "state_code": "99", "trade_name": null}, "amounts": {"discount": null, "subtotal": 140000.0, "round_off": null, "total_tax": 25200.0, "tds_amount": null, "amount_paid": null, "balance_due": null, "cess_amount": null, "cgst_amount": 12600.0, "grand_total": 165200.0, "igst_amount": null, "sgst_amount": 12600.0, "ugst_amount": null, "other_charges": null, "taxable_amount": 140000.0, "freight_charges": null, "handling_charges": null, "shipping_charges": null}, "payment": {"branch": null, "upi_id": null, "bank_name": null, "ifsc_code": null, "swift_code": null, "account_name": null, "payment_terms": "Net 30 Days", "account_number": null}, "document": {"currency": "INR", "due_date": "2026-09-17", "invoice_date": "2026-08-18", "invoice_type": "TAX_INVOICE", "document_type": "invoice", "invoice_number": "INV-2026-00942", "original_filename": "system_generated_sample_invoice_gstin_9924USA29003OSI.pdf"}, "reference": {"po_date": null, "po_number": "PO-2026-00421", "order_number": null, "quotation_date": null, "contract_number": null, "quotation_number": null, "reference_number": null, "delivery_note_date": null, "delivery_note_number": null}, "compliance": {"irn": null, "qr_code_data": null, "export_invoice": null, "reverse_charge": false, "einvoice_status": null, "acknowledgement_date": null, "acknowledgement_number": null}, "extraction": {"job_id": "4383b9379b40118d68b16c2254f31819dd8d31c470552efad8e89e9d565fd044", "status": "SUCCESS", "provider": "AWS_TEXTRACT", "warnings": [], "confidence": 92.69886798393435, "field_details": {"hsn_sac": {"page": null, "value": "997331", "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "due_date": {"page": 1, "value": "17-Sep-2026", "source": "TEXTRACT_SUMMARY", "confidence": 99.92374420166016, "extraction_method": "TEXTRACT_SUMMARY"}, "subtotal": {"page": 1, "value": "140,000.00", "source": "TEXTRACT_SUMMARY", "confidence": 99.98973846435547, "extraction_method": "TEXTRACT_SUMMARY"}, "tax_type": {"page": null, "value": "INTRA_STATE_CGST_SGST", "source": "DERIVED", "confidence": null, "extraction_method": "DERIVED"}, "buyer_pan": {"page": null, "value": "AABCA1234F", "source": "DERIVED_FROM_GSTIN", "confidence": 85, "extraction_method": "DERIVED"}, "cgst_rate": {"page": null, "value": 9, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "po_number": {"page": 1, "value": "PO-2026-00421", "source": "TEXTRACT_SUMMARY", "confidence": 99.95179748535156, "extraction_method": "TEXTRACT_SUMMARY"}, "sgst_rate": {"page": null, "value": 9, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "total_tax": {"page": null, "value": 25200, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "DERIVED"}, "buyer_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "source": "TEXTRACT_SUMMARY", "confidence": 99.9197006225586, "extraction_method": "TEXTRACT_SUMMARY"}, "buyer_gstin": {"page": null, "value": "36AABCA1234F1Z5", "source": "REGEX_FULLTEXT_ANCHORED", "confidence": 85, "extraction_method": "REGEX"}, "cgst_amount": {"page": null, "value": 12600, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "grand_total": {"page": 1, "value": "165,200.00", "source": "TEXTRACT_SUMMARY", "confidence": 99.92138671875, "extraction_method": "TEXTRACT_SUMMARY"}, "sgst_amount": {"page": null, "value": 12600, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "vendor_name": {"page": 1, "value": "Global Software Solutions Pvt. Ltd.", "source": "TEXTRACT_SUMMARY", "confidence": 98.18354034423828, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_date": {"page": 1, "value": "18-Aug-2026", "source": "TEXTRACT_SUMMARY", "confidence": 99.97993469238281, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_type": {"page": null, "value": "TAX_INVOICE", "source": "REGEX_FULLTEXT", "confidence": 80, "extraction_method": "REGEX"}, "vendor_gstin": {"page": 1, "value": "9924USA29003OSI", "source": "TEXTRACT_QUERY", "confidence": 98, "extraction_method": "TEXTRACT_QUERY"}, "buyer_address": {"page": 1, "value": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\nHyderabad, Telangana 500081\\n-\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36", "source": "TEXTRACT_SUMMARY", "confidence": 97.92948913574219, "extraction_method": "TEXTRACT_SUMMARY"}, "payment_terms": {"page": 1, "value": "Net 30 Days", "source": "TEXTRACT_SUMMARY", "confidence": 99.6680908203125, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_number": {"page": 1, "value": "INV-2026-00942", "source": "TEXTRACT_SUMMARY", "confidence": 98.63064575195312, "extraction_method": "TEXTRACT_SUMMARY"}, "reverse_charge": {"page": 1, "value": false, "source": "TEXTRACT_QUERY", "confidence": 75, "extraction_method": "TEXTRACT_QUERY"}, "taxable_amount": {"page": 1, "value": 140000, "source": "TEXTRACT_QUERY", "confidence": 94, "extraction_method": "TEXTRACT_QUERY"}, "vendor_address": {"page": 1, "value": "Global Software Solutions Pvt. Ltd.\\n5th Floor, Tech Park, Hitech City\\nHyderabad, Telangana 500081\\n-", "source": "TEXTRACT_SUMMARY", "confidence": 97.93276977539062, "extraction_method": "TEXTRACT_SUMMARY"}, "place_of_supply": {"page": 1, "value": "Telangana", "source": "TEXTRACT_QUERY", "confidence": 98, "extraction_method": "TEXTRACT_QUERY"}, "buyer_legal_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "source": "TEXTRACT_SUMMARY", "confidence": 99.79057312011719, "extraction_method": "TEXTRACT_SUMMARY"}, "vendor_legal_name": {"page": 1, "value": "Global Software Solutions Pvt. Ltd.", "source": "TEXTRACT_SUMMARY", "confidence": 98.18354034423828, "extraction_method": "TEXTRACT_SUMMARY"}, "buyer_shipping_address": {"page": 1, "value": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\n-\\nHyderabad, Telangana 500081\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36", "source": "TEXTRACT_SUMMARY", "confidence": 98.21762084960938, "extraction_method": "TEXTRACT_SUMMARY"}}, "field_sources": {"hsn_sac": "REGEX_FULLTEXT", "due_date": "TEXTRACT_SUMMARY", "subtotal": "TEXTRACT_SUMMARY", "buyer_pan": "DERIVED_FROM_GSTIN", "cgst_rate": "REGEX_FULLTEXT", "po_number": "TEXTRACT_SUMMARY", "sgst_rate": "REGEX_FULLTEXT", "total_tax": "REGEX_FULLTEXT", "buyer_name": "TEXTRACT_SUMMARY", "buyer_gstin": "REGEX_FULLTEXT_ANCHORED", "cgst_amount": "REGEX_FULLTEXT", "grand_total": "TEXTRACT_SUMMARY", "sgst_amount": "REGEX_FULLTEXT", "vendor_name": "TEXTRACT_SUMMARY", "invoice_date": "TEXTRACT_SUMMARY", "invoice_type": "REGEX_FULLTEXT", "vendor_gstin": "TEXTRACT_QUERY", "buyer_address": "TEXTRACT_SUMMARY", "payment_terms": "TEXTRACT_SUMMARY", "invoice_number": "TEXTRACT_SUMMARY", "reverse_charge": "TEXTRACT_QUERY", "taxable_amount": "TEXTRACT_QUERY", "vendor_address": "TEXTRACT_SUMMARY", "place_of_supply": "TEXTRACT_QUERY", "buyer_legal_name": "TEXTRACT_SUMMARY", "vendor_legal_name": "TEXTRACT_SUMMARY", "buyer_shipping_address": "TEXTRACT_SUMMARY"}, "pages_processed": 1, "field_confidence": {"hsn_sac": 75.0, "due_date": 99.92374420166016, "subtotal": 99.98973846435547, "buyer_pan": 85.0, "cgst_rate": 75.0, "po_number": 99.95179748535156, "sgst_rate": 75.0, "total_tax": 75.0, "buyer_name": 99.9197006225586, "buyer_gstin": 85.0, "cgst_amount": 75.0, "grand_total": 99.92138671875, "sgst_amount": 75.0, "vendor_name": 98.18354034423828, "invoice_date": 99.97993469238281, "invoice_type": 80.0, "vendor_gstin": 98.0, "buyer_address": 97.92948913574219, "payment_terms": 99.6680908203125, "invoice_number": 98.63064575195312, "reverse_charge": 75.0, "taxable_amount": 94.0, "vendor_address": 97.93276977539062, "place_of_supply": 98.0, "buyer_legal_name": 99.79057312011719, "vendor_legal_name": 98.18354034423828, "buyer_shipping_address": 98.21762084960938}}, "raw_fields": {"query_results": {"IFSC": {"page": 1, "value": "997331", "confidence": 52}, "BUYER_GSTIN": {"page": 1, "value": "9924USA29003OSI", "confidence": 93}, "GRAND_TOTAL": {"page": 1, "value": "165,200.00", "confidence": 95}, "BANK_DETAILS": {"page": 1, "value": "9924USA29003OSI", "confidence": 90}, "SELLER_GSTIN": {"page": 1, "value": "9924USA29003OSI", "confidence": 98}, "PAYMENT_TERMS": {"page": 1, "value": "Net 30 Days", "confidence": 92}, "REVERSE_CHARGE": {"page": 1, "value": "No", "confidence": 75}, "TAXABLE_AMOUNT": {"page": 1, "value": "INR 1,40,000.00", "confidence": 94}, "PLACE_OF_SUPPLY": {"page": 1, "value": "Telangana", "confidence": 98}}}, "validation": {"issues": ["Vendor GSTIN '9924USA29003OSI' does not match the expected GSTIN structure."], "status": "REVIEW_REQUIRED", "is_valid": false, "warnings": [], "field_issues": [{"code": "INVALID_GSTIN_FORMAT", "field": "vendor_gstin", "message": "Vendor GSTIN '9924USA29003OSI' does not match the expected GSTIN structure."}], "tax_difference": 0.0, "total_difference": 0.0}, "invoice_lines": [{"unit": null, "hsn_sac": "997331", "discount": null, "quantity": 1.0, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": null, "unit_price": 100000.0, "cess_amount": null, "cgst_amount": null, "description": "Cloud ERP Software Subscription", "igst_amount": null, "line_number": 1, "sgst_amount": null, "ugst_amount": null, "product_code": "997331", "taxable_amount": null}, {"unit": null, "hsn_sac": "997331", "discount": null, "quantity": 1.0, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": null, "unit_price": 40000.0, "cess_amount": null, "cgst_amount": null, "description": "Implementation and Professional Services", "igst_amount": null, "line_number": 2, "sgst_amount": null, "ugst_amount": null, "product_code": "997331", "taxable_amount": null}]}	\N	\N	2026-08-20 12:24:07.991985
28	UPLOAD	\N	\N	\N	2026-08-21 14:11:35.014627	system_generated_sample_invoice_gstin_9924USA29003OSI.pdf	invoices/2026/08/1993710584c84f62a1a1a3fb65c51a8e_system_generated_sample_invoice_gstin_9924USA29003OSI.pdf	REVIEW_REQUIRED	\N	{"tax": {"hsn_sac": "997331", "tax_type": "INTRA_STATE_CGST_SGST", "cess_rate": null, "cgst_rate": 9.0, "igst_rate": null, "sgst_rate": 9.0, "ugst_rate": null, "reverse_charge": false, "place_of_supply": "Telangana"}, "buyer": {"pan": "AABCA1234F", "name": "Apex Business Solutions Private Limited", "email": null, "gstin": "36AABCA1234F1Z5", "phone": null, "state": "Telangana", "address": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\nHyderabad, Telangana 500081\\n-\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36", "country": null, "legal_name": "Apex Business Solutions Private Limited", "state_code": "36", "trade_name": null, "shipping_address": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\n-\\nHyderabad, Telangana 500081\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36"}, "vendor": {"pan": null, "name": "Global Software Solutions Pvt. Ltd.", "email": null, "gstin": "9924USA29003OSI", "phone": null, "state": null, "address": "Global Software Solutions Pvt. Ltd.\\n5th Floor, Tech Park, Hitech City\\nHyderabad, Telangana 500081\\n-", "country": null, "website": null, "legal_name": "Global Software Solutions Pvt. Ltd.", "state_code": "99", "trade_name": null}, "amounts": {"discount": null, "subtotal": 140000.0, "round_off": null, "total_tax": 25200.0, "tds_amount": null, "amount_paid": null, "balance_due": null, "cess_amount": null, "cgst_amount": 12600.0, "grand_total": 165200.0, "igst_amount": null, "sgst_amount": 12600.0, "ugst_amount": null, "other_charges": null, "taxable_amount": 140000.0, "freight_charges": null, "handling_charges": null, "shipping_charges": null}, "payment": {"branch": null, "upi_id": null, "bank_name": null, "ifsc_code": null, "swift_code": null, "account_name": null, "payment_terms": "Net 30 Days", "account_number": null}, "document": {"currency": "INR", "due_date": "2026-09-17", "invoice_date": "2026-08-18", "invoice_type": "TAX_INVOICE", "document_type": "invoice", "invoice_number": "INV-2026-00942", "original_filename": "system_generated_sample_invoice_gstin_9924USA29003OSI.pdf"}, "reference": {"po_date": null, "po_number": "PO-2026-00421", "order_number": null, "quotation_date": null, "contract_number": null, "quotation_number": null, "reference_number": null, "delivery_note_date": null, "delivery_note_number": null}, "compliance": {"irn": null, "qr_code_data": null, "export_invoice": null, "reverse_charge": false, "einvoice_status": null, "acknowledgement_date": null, "acknowledgement_number": null}, "extraction": {"job_id": "f517fad1ceb957ee89011b66975f2e3931ff3d8c114cf77ea288d79c708427a5", "status": "SUCCESS", "provider": "AWS_TEXTRACT", "warnings": [], "confidence": 92.69886798393435, "field_details": {"hsn_sac": {"page": null, "value": "997331", "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "due_date": {"page": 1, "value": "17-Sep-2026", "source": "TEXTRACT_SUMMARY", "confidence": 99.92374420166016, "extraction_method": "TEXTRACT_SUMMARY"}, "subtotal": {"page": 1, "value": "140,000.00", "source": "TEXTRACT_SUMMARY", "confidence": 99.98973846435547, "extraction_method": "TEXTRACT_SUMMARY"}, "tax_type": {"page": null, "value": "INTRA_STATE_CGST_SGST", "source": "DERIVED", "confidence": null, "extraction_method": "DERIVED"}, "buyer_pan": {"page": null, "value": "AABCA1234F", "source": "DERIVED_FROM_GSTIN", "confidence": 85, "extraction_method": "DERIVED"}, "cgst_rate": {"page": null, "value": 9, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "po_number": {"page": 1, "value": "PO-2026-00421", "source": "TEXTRACT_SUMMARY", "confidence": 99.95179748535156, "extraction_method": "TEXTRACT_SUMMARY"}, "sgst_rate": {"page": null, "value": 9, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "total_tax": {"page": null, "value": 25200, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "DERIVED"}, "buyer_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "source": "TEXTRACT_SUMMARY", "confidence": 99.9197006225586, "extraction_method": "TEXTRACT_SUMMARY"}, "buyer_gstin": {"page": null, "value": "36AABCA1234F1Z5", "source": "REGEX_FULLTEXT_ANCHORED", "confidence": 85, "extraction_method": "REGEX"}, "cgst_amount": {"page": null, "value": 12600, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "grand_total": {"page": 1, "value": "165,200.00", "source": "TEXTRACT_SUMMARY", "confidence": 99.92138671875, "extraction_method": "TEXTRACT_SUMMARY"}, "sgst_amount": {"page": null, "value": 12600, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "vendor_name": {"page": 1, "value": "Global Software Solutions Pvt. Ltd.", "source": "TEXTRACT_SUMMARY", "confidence": 98.18354034423828, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_date": {"page": 1, "value": "18-Aug-2026", "source": "TEXTRACT_SUMMARY", "confidence": 99.97993469238281, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_type": {"page": null, "value": "TAX_INVOICE", "source": "REGEX_FULLTEXT", "confidence": 80, "extraction_method": "REGEX"}, "vendor_gstin": {"page": 1, "value": "9924USA29003OSI", "source": "TEXTRACT_QUERY", "confidence": 98, "extraction_method": "TEXTRACT_QUERY"}, "buyer_address": {"page": 1, "value": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\nHyderabad, Telangana 500081\\n-\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36", "source": "TEXTRACT_SUMMARY", "confidence": 97.92948913574219, "extraction_method": "TEXTRACT_SUMMARY"}, "payment_terms": {"page": 1, "value": "Net 30 Days", "source": "TEXTRACT_SUMMARY", "confidence": 99.6680908203125, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_number": {"page": 1, "value": "INV-2026-00942", "source": "TEXTRACT_SUMMARY", "confidence": 98.63064575195312, "extraction_method": "TEXTRACT_SUMMARY"}, "reverse_charge": {"page": 1, "value": false, "source": "TEXTRACT_QUERY", "confidence": 75, "extraction_method": "TEXTRACT_QUERY"}, "taxable_amount": {"page": 1, "value": 140000, "source": "TEXTRACT_QUERY", "confidence": 94, "extraction_method": "TEXTRACT_QUERY"}, "vendor_address": {"page": 1, "value": "Global Software Solutions Pvt. Ltd.\\n5th Floor, Tech Park, Hitech City\\nHyderabad, Telangana 500081\\n-", "source": "TEXTRACT_SUMMARY", "confidence": 97.93276977539062, "extraction_method": "TEXTRACT_SUMMARY"}, "place_of_supply": {"page": 1, "value": "Telangana", "source": "TEXTRACT_QUERY", "confidence": 98, "extraction_method": "TEXTRACT_QUERY"}, "buyer_legal_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "source": "TEXTRACT_SUMMARY", "confidence": 99.79057312011719, "extraction_method": "TEXTRACT_SUMMARY"}, "vendor_legal_name": {"page": 1, "value": "Global Software Solutions Pvt. Ltd.", "source": "TEXTRACT_SUMMARY", "confidence": 98.18354034423828, "extraction_method": "TEXTRACT_SUMMARY"}, "buyer_shipping_address": {"page": 1, "value": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\n-\\nHyderabad, Telangana 500081\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36", "source": "TEXTRACT_SUMMARY", "confidence": 98.21762084960938, "extraction_method": "TEXTRACT_SUMMARY"}}, "field_sources": {"hsn_sac": "REGEX_FULLTEXT", "due_date": "TEXTRACT_SUMMARY", "subtotal": "TEXTRACT_SUMMARY", "buyer_pan": "DERIVED_FROM_GSTIN", "cgst_rate": "REGEX_FULLTEXT", "po_number": "TEXTRACT_SUMMARY", "sgst_rate": "REGEX_FULLTEXT", "total_tax": "REGEX_FULLTEXT", "buyer_name": "TEXTRACT_SUMMARY", "buyer_gstin": "REGEX_FULLTEXT_ANCHORED", "cgst_amount": "REGEX_FULLTEXT", "grand_total": "TEXTRACT_SUMMARY", "sgst_amount": "REGEX_FULLTEXT", "vendor_name": "TEXTRACT_SUMMARY", "invoice_date": "TEXTRACT_SUMMARY", "invoice_type": "REGEX_FULLTEXT", "vendor_gstin": "TEXTRACT_QUERY", "buyer_address": "TEXTRACT_SUMMARY", "payment_terms": "TEXTRACT_SUMMARY", "invoice_number": "TEXTRACT_SUMMARY", "reverse_charge": "TEXTRACT_QUERY", "taxable_amount": "TEXTRACT_QUERY", "vendor_address": "TEXTRACT_SUMMARY", "place_of_supply": "TEXTRACT_QUERY", "buyer_legal_name": "TEXTRACT_SUMMARY", "vendor_legal_name": "TEXTRACT_SUMMARY", "buyer_shipping_address": "TEXTRACT_SUMMARY"}, "pages_processed": 1, "field_confidence": {"hsn_sac": 75.0, "due_date": 99.92374420166016, "subtotal": 99.98973846435547, "buyer_pan": 85.0, "cgst_rate": 75.0, "po_number": 99.95179748535156, "sgst_rate": 75.0, "total_tax": 75.0, "buyer_name": 99.9197006225586, "buyer_gstin": 85.0, "cgst_amount": 75.0, "grand_total": 99.92138671875, "sgst_amount": 75.0, "vendor_name": 98.18354034423828, "invoice_date": 99.97993469238281, "invoice_type": 80.0, "vendor_gstin": 98.0, "buyer_address": 97.92948913574219, "payment_terms": 99.6680908203125, "invoice_number": 98.63064575195312, "reverse_charge": 75.0, "taxable_amount": 94.0, "vendor_address": 97.93276977539062, "place_of_supply": 98.0, "buyer_legal_name": 99.79057312011719, "vendor_legal_name": 98.18354034423828, "buyer_shipping_address": 98.21762084960938}}, "raw_fields": {"query_results": {"IFSC": {"page": 1, "value": "997331", "confidence": 52}, "BUYER_GSTIN": {"page": 1, "value": "9924USA29003OSI", "confidence": 93}, "GRAND_TOTAL": {"page": 1, "value": "165,200.00", "confidence": 95}, "BANK_DETAILS": {"page": 1, "value": "9924USA29003OSI", "confidence": 90}, "SELLER_GSTIN": {"page": 1, "value": "9924USA29003OSI", "confidence": 98}, "PAYMENT_TERMS": {"page": 1, "value": "Net 30 Days", "confidence": 92}, "REVERSE_CHARGE": {"page": 1, "value": "No", "confidence": 75}, "TAXABLE_AMOUNT": {"page": 1, "value": "INR 1,40,000.00", "confidence": 94}, "PLACE_OF_SUPPLY": {"page": 1, "value": "Telangana", "confidence": 98}}}, "validation": {"issues": ["Vendor GSTIN '9924USA29003OSI' does not match the expected GSTIN structure."], "status": "REVIEW_REQUIRED", "is_valid": false, "warnings": [], "field_issues": [{"code": "INVALID_GSTIN_FORMAT", "field": "vendor_gstin", "message": "Vendor GSTIN '9924USA29003OSI' does not match the expected GSTIN structure."}], "tax_difference": 0.0, "total_difference": 0.0}, "invoice_lines": [{"unit": null, "hsn_sac": "997331", "discount": null, "quantity": 1.0, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": null, "unit_price": 100000.0, "cess_amount": null, "cgst_amount": null, "description": "Cloud ERP Software Subscription", "igst_amount": null, "line_number": 1, "sgst_amount": null, "ugst_amount": null, "product_code": "997331", "taxable_amount": null}, {"unit": null, "hsn_sac": "997331", "discount": null, "quantity": 1.0, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": null, "unit_price": 40000.0, "cess_amount": null, "cgst_amount": null, "description": "Implementation and Professional Services", "igst_amount": null, "line_number": 2, "sgst_amount": null, "ugst_amount": null, "product_code": "997331", "taxable_amount": null}]}	\N	\N	2026-08-21 14:11:35.014627
29	UPLOAD	\N	\N	\N	2026-08-24 05:31:50.402756	system_generated_sample_invoice_gstin_9924USA29003OSI.pdf	invoices/2026/08/b733a45def0c4d6da669e85c5bf71dd2_system_generated_sample_invoice_gstin_9924USA29003OSI.pdf	REVIEW_REQUIRED	\N	{"tax": {"hsn_sac": "997331", "tax_type": "INTRA_STATE_CGST_SGST", "cess_rate": null, "cgst_rate": 9.0, "igst_rate": null, "sgst_rate": 9.0, "ugst_rate": null, "reverse_charge": false, "place_of_supply": "Telangana"}, "buyer": {"pan": "AABCA1234F", "name": "Apex Business Solutions Private Limited", "email": null, "gstin": "36AABCA1234F1Z5", "phone": null, "state": "Telangana", "address": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\nHyderabad, Telangana 500081\\n-\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36", "country": null, "legal_name": "Apex Business Solutions Private Limited", "state_code": "36", "trade_name": null, "shipping_address": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\n-\\nHyderabad, Telangana 500081\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36"}, "vendor": {"pan": null, "name": "Global Software Solutions Pvt. Ltd.", "email": null, "gstin": "9924USA29003OSI", "phone": null, "state": null, "address": "Global Software Solutions Pvt. Ltd.\\n5th Floor, Tech Park, Hitech City\\nHyderabad, Telangana 500081\\n-", "country": null, "website": null, "legal_name": "Global Software Solutions Pvt. Ltd.", "state_code": "99", "trade_name": null}, "amounts": {"discount": null, "subtotal": 140000.0, "round_off": null, "total_tax": 25200.0, "tds_amount": null, "amount_paid": null, "balance_due": null, "cess_amount": null, "cgst_amount": 12600.0, "grand_total": 165200.0, "igst_amount": null, "sgst_amount": 12600.0, "ugst_amount": null, "other_charges": null, "taxable_amount": 140000.0, "freight_charges": null, "handling_charges": null, "shipping_charges": null}, "payment": {"branch": null, "upi_id": null, "bank_name": null, "ifsc_code": null, "swift_code": null, "account_name": null, "payment_terms": "Net 30 Days", "account_number": null}, "document": {"currency": "INR", "due_date": "2026-09-17", "invoice_date": "2026-08-18", "invoice_type": "TAX_INVOICE", "document_type": "invoice", "invoice_number": "INV-2026-00942", "original_filename": "system_generated_sample_invoice_gstin_9924USA29003OSI.pdf"}, "reference": {"po_date": null, "po_number": "PO-2026-00421", "order_number": null, "quotation_date": null, "contract_number": null, "quotation_number": null, "reference_number": null, "delivery_note_date": null, "delivery_note_number": null}, "compliance": {"irn": null, "qr_code_data": null, "export_invoice": null, "reverse_charge": false, "einvoice_status": null, "acknowledgement_date": null, "acknowledgement_number": null}, "extraction": {"job_id": "51a4b0823c79c1feebc9db22acd64bafec1dce2f71c0409e3c888fe647744842", "status": "SUCCESS", "provider": "AWS_TEXTRACT", "warnings": [], "confidence": 92.69886798393435, "field_details": {"hsn_sac": {"page": null, "value": "997331", "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "due_date": {"page": 1, "value": "17-Sep-2026", "source": "TEXTRACT_SUMMARY", "confidence": 99.92374420166016, "extraction_method": "TEXTRACT_SUMMARY"}, "subtotal": {"page": 1, "value": "140,000.00", "source": "TEXTRACT_SUMMARY", "confidence": 99.98973846435547, "extraction_method": "TEXTRACT_SUMMARY"}, "tax_type": {"page": null, "value": "INTRA_STATE_CGST_SGST", "source": "DERIVED", "confidence": null, "extraction_method": "DERIVED"}, "buyer_pan": {"page": null, "value": "AABCA1234F", "source": "DERIVED_FROM_GSTIN", "confidence": 85, "extraction_method": "DERIVED"}, "cgst_rate": {"page": null, "value": 9, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "po_number": {"page": 1, "value": "PO-2026-00421", "source": "TEXTRACT_SUMMARY", "confidence": 99.95179748535156, "extraction_method": "TEXTRACT_SUMMARY"}, "sgst_rate": {"page": null, "value": 9, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "total_tax": {"page": null, "value": 25200, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "DERIVED"}, "buyer_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "source": "TEXTRACT_SUMMARY", "confidence": 99.9197006225586, "extraction_method": "TEXTRACT_SUMMARY"}, "buyer_gstin": {"page": null, "value": "36AABCA1234F1Z5", "source": "REGEX_FULLTEXT_ANCHORED", "confidence": 85, "extraction_method": "REGEX"}, "cgst_amount": {"page": null, "value": 12600, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "grand_total": {"page": 1, "value": "165,200.00", "source": "TEXTRACT_SUMMARY", "confidence": 99.92138671875, "extraction_method": "TEXTRACT_SUMMARY"}, "sgst_amount": {"page": null, "value": 12600, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "vendor_name": {"page": 1, "value": "Global Software Solutions Pvt. Ltd.", "source": "TEXTRACT_SUMMARY", "confidence": 98.18354034423828, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_date": {"page": 1, "value": "18-Aug-2026", "source": "TEXTRACT_SUMMARY", "confidence": 99.97993469238281, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_type": {"page": null, "value": "TAX_INVOICE", "source": "REGEX_FULLTEXT", "confidence": 80, "extraction_method": "REGEX"}, "vendor_gstin": {"page": 1, "value": "9924USA29003OSI", "source": "TEXTRACT_QUERY", "confidence": 98, "extraction_method": "TEXTRACT_QUERY"}, "buyer_address": {"page": 1, "value": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\nHyderabad, Telangana 500081\\n-\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36", "source": "TEXTRACT_SUMMARY", "confidence": 97.92948913574219, "extraction_method": "TEXTRACT_SUMMARY"}, "payment_terms": {"page": 1, "value": "Net 30 Days", "source": "TEXTRACT_SUMMARY", "confidence": 99.6680908203125, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_number": {"page": 1, "value": "INV-2026-00942", "source": "TEXTRACT_SUMMARY", "confidence": 98.63064575195312, "extraction_method": "TEXTRACT_SUMMARY"}, "reverse_charge": {"page": 1, "value": false, "source": "TEXTRACT_QUERY", "confidence": 75, "extraction_method": "TEXTRACT_QUERY"}, "taxable_amount": {"page": 1, "value": 140000, "source": "TEXTRACT_QUERY", "confidence": 94, "extraction_method": "TEXTRACT_QUERY"}, "vendor_address": {"page": 1, "value": "Global Software Solutions Pvt. Ltd.\\n5th Floor, Tech Park, Hitech City\\nHyderabad, Telangana 500081\\n-", "source": "TEXTRACT_SUMMARY", "confidence": 97.93276977539062, "extraction_method": "TEXTRACT_SUMMARY"}, "place_of_supply": {"page": 1, "value": "Telangana", "source": "TEXTRACT_QUERY", "confidence": 98, "extraction_method": "TEXTRACT_QUERY"}, "buyer_legal_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "source": "TEXTRACT_SUMMARY", "confidence": 99.79057312011719, "extraction_method": "TEXTRACT_SUMMARY"}, "vendor_legal_name": {"page": 1, "value": "Global Software Solutions Pvt. Ltd.", "source": "TEXTRACT_SUMMARY", "confidence": 98.18354034423828, "extraction_method": "TEXTRACT_SUMMARY"}, "buyer_shipping_address": {"page": 1, "value": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\n-\\nHyderabad, Telangana 500081\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36", "source": "TEXTRACT_SUMMARY", "confidence": 98.21762084960938, "extraction_method": "TEXTRACT_SUMMARY"}}, "field_sources": {"hsn_sac": "REGEX_FULLTEXT", "due_date": "TEXTRACT_SUMMARY", "subtotal": "TEXTRACT_SUMMARY", "buyer_pan": "DERIVED_FROM_GSTIN", "cgst_rate": "REGEX_FULLTEXT", "po_number": "TEXTRACT_SUMMARY", "sgst_rate": "REGEX_FULLTEXT", "total_tax": "REGEX_FULLTEXT", "buyer_name": "TEXTRACT_SUMMARY", "buyer_gstin": "REGEX_FULLTEXT_ANCHORED", "cgst_amount": "REGEX_FULLTEXT", "grand_total": "TEXTRACT_SUMMARY", "sgst_amount": "REGEX_FULLTEXT", "vendor_name": "TEXTRACT_SUMMARY", "invoice_date": "TEXTRACT_SUMMARY", "invoice_type": "REGEX_FULLTEXT", "vendor_gstin": "TEXTRACT_QUERY", "buyer_address": "TEXTRACT_SUMMARY", "payment_terms": "TEXTRACT_SUMMARY", "invoice_number": "TEXTRACT_SUMMARY", "reverse_charge": "TEXTRACT_QUERY", "taxable_amount": "TEXTRACT_QUERY", "vendor_address": "TEXTRACT_SUMMARY", "place_of_supply": "TEXTRACT_QUERY", "buyer_legal_name": "TEXTRACT_SUMMARY", "vendor_legal_name": "TEXTRACT_SUMMARY", "buyer_shipping_address": "TEXTRACT_SUMMARY"}, "pages_processed": 1, "field_confidence": {"hsn_sac": 75.0, "due_date": 99.92374420166016, "subtotal": 99.98973846435547, "buyer_pan": 85.0, "cgst_rate": 75.0, "po_number": 99.95179748535156, "sgst_rate": 75.0, "total_tax": 75.0, "buyer_name": 99.9197006225586, "buyer_gstin": 85.0, "cgst_amount": 75.0, "grand_total": 99.92138671875, "sgst_amount": 75.0, "vendor_name": 98.18354034423828, "invoice_date": 99.97993469238281, "invoice_type": 80.0, "vendor_gstin": 98.0, "buyer_address": 97.92948913574219, "payment_terms": 99.6680908203125, "invoice_number": 98.63064575195312, "reverse_charge": 75.0, "taxable_amount": 94.0, "vendor_address": 97.93276977539062, "place_of_supply": 98.0, "buyer_legal_name": 99.79057312011719, "vendor_legal_name": 98.18354034423828, "buyer_shipping_address": 98.21762084960938}}, "raw_fields": {"query_results": {"IFSC": {"page": 1, "value": "997331", "confidence": 52}, "BUYER_GSTIN": {"page": 1, "value": "9924USA29003OSI", "confidence": 93}, "GRAND_TOTAL": {"page": 1, "value": "165,200.00", "confidence": 95}, "BANK_DETAILS": {"page": 1, "value": "9924USA29003OSI", "confidence": 90}, "SELLER_GSTIN": {"page": 1, "value": "9924USA29003OSI", "confidence": 98}, "PAYMENT_TERMS": {"page": 1, "value": "Net 30 Days", "confidence": 92}, "REVERSE_CHARGE": {"page": 1, "value": "No", "confidence": 75}, "TAXABLE_AMOUNT": {"page": 1, "value": "INR 1,40,000.00", "confidence": 94}, "PLACE_OF_SUPPLY": {"page": 1, "value": "Telangana", "confidence": 98}}}, "validation": {"issues": ["Vendor GSTIN '9924USA29003OSI' does not match the expected GSTIN structure."], "status": "REVIEW_REQUIRED", "is_valid": false, "warnings": [], "field_issues": [{"code": "INVALID_GSTIN_FORMAT", "field": "vendor_gstin", "message": "Vendor GSTIN '9924USA29003OSI' does not match the expected GSTIN structure."}], "tax_difference": 0.0, "total_difference": 0.0}, "invoice_lines": [{"unit": null, "hsn_sac": "997331", "discount": null, "quantity": 1.0, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": null, "unit_price": 100000.0, "cess_amount": null, "cgst_amount": null, "description": "Cloud ERP Software Subscription", "igst_amount": null, "line_number": 1, "sgst_amount": null, "ugst_amount": null, "product_code": "997331", "taxable_amount": null}, {"unit": null, "hsn_sac": "997331", "discount": null, "quantity": 1.0, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": null, "unit_price": 40000.0, "cess_amount": null, "cgst_amount": null, "description": "Implementation and Professional Services", "igst_amount": null, "line_number": 2, "sgst_amount": null, "ugst_amount": null, "product_code": "997331", "taxable_amount": null}]}	\N	\N	2026-08-24 05:31:50.402756
30	UPLOAD	\N	\N	\N	2026-08-24 05:42:48.505497	system_generated_sample_invoice_gstin_9924USA29003OSI.pdf	invoices/2026/08/689d156dcc704f5f9907c7d5f6001ce7_system_generated_sample_invoice_gstin_9924USA29003OSI.pdf	REVIEW_REQUIRED	\N	{"tax": {"hsn_sac": "997331", "tax_type": "INTRA_STATE_CGST_SGST", "cess_rate": null, "cgst_rate": 9.0, "igst_rate": null, "sgst_rate": 9.0, "ugst_rate": null, "reverse_charge": false, "place_of_supply": "Telangana"}, "buyer": {"pan": "AABCA1234F", "name": "Apex Business Solutions Private Limited", "email": null, "gstin": "36AABCA1234F1Z5", "phone": null, "state": "Telangana", "address": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\nHyderabad, Telangana 500081\\n-\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36", "country": null, "legal_name": "Apex Business Solutions Private Limited", "state_code": "36", "trade_name": null, "shipping_address": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\n-\\nHyderabad, Telangana 500081\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36"}, "vendor": {"pan": null, "name": "Global Software Solutions Pvt. Ltd.", "email": null, "gstin": "9924USA29003OSI", "phone": null, "state": null, "address": "Global Software Solutions Pvt. Ltd.\\n5th Floor, Tech Park, Hitech City\\nHyderabad, Telangana 500081\\n-", "country": null, "website": null, "legal_name": "Global Software Solutions Pvt. Ltd.", "state_code": "99", "trade_name": null}, "amounts": {"discount": null, "subtotal": 140000.0, "round_off": null, "total_tax": 25200.0, "tds_amount": null, "amount_paid": null, "balance_due": null, "cess_amount": null, "cgst_amount": 12600.0, "grand_total": 165200.0, "igst_amount": null, "sgst_amount": 12600.0, "ugst_amount": null, "other_charges": null, "taxable_amount": 140000.0, "freight_charges": null, "handling_charges": null, "shipping_charges": null}, "payment": {"branch": null, "upi_id": null, "bank_name": null, "ifsc_code": null, "swift_code": null, "account_name": null, "payment_terms": "Net 30 Days", "account_number": null}, "document": {"currency": "INR", "due_date": "2026-09-17", "invoice_date": "2026-08-18", "invoice_type": "TAX_INVOICE", "document_type": "invoice", "invoice_number": "INV-2026-00942", "original_filename": "system_generated_sample_invoice_gstin_9924USA29003OSI.pdf"}, "reference": {"po_date": null, "po_number": "PO-2026-00421", "order_number": null, "quotation_date": null, "contract_number": null, "quotation_number": null, "reference_number": null, "delivery_note_date": null, "delivery_note_number": null}, "compliance": {"irn": null, "qr_code_data": null, "export_invoice": null, "reverse_charge": false, "einvoice_status": null, "acknowledgement_date": null, "acknowledgement_number": null}, "extraction": {"job_id": "d44b261135406290a2ecdc349663ab3491825c56e21481dab1c1770cf20cfd1b", "status": "SUCCESS", "provider": "AWS_TEXTRACT", "warnings": [], "confidence": 92.69886798393435, "field_details": {"hsn_sac": {"page": null, "value": "997331", "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "due_date": {"page": 1, "value": "17-Sep-2026", "source": "TEXTRACT_SUMMARY", "confidence": 99.92374420166016, "extraction_method": "TEXTRACT_SUMMARY"}, "subtotal": {"page": 1, "value": "140,000.00", "source": "TEXTRACT_SUMMARY", "confidence": 99.98973846435547, "extraction_method": "TEXTRACT_SUMMARY"}, "tax_type": {"page": null, "value": "INTRA_STATE_CGST_SGST", "source": "DERIVED", "confidence": null, "extraction_method": "DERIVED"}, "buyer_pan": {"page": null, "value": "AABCA1234F", "source": "DERIVED_FROM_GSTIN", "confidence": 85, "extraction_method": "DERIVED"}, "cgst_rate": {"page": null, "value": 9, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "po_number": {"page": 1, "value": "PO-2026-00421", "source": "TEXTRACT_SUMMARY", "confidence": 99.95179748535156, "extraction_method": "TEXTRACT_SUMMARY"}, "sgst_rate": {"page": null, "value": 9, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "total_tax": {"page": null, "value": 25200, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "DERIVED"}, "buyer_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "source": "TEXTRACT_SUMMARY", "confidence": 99.9197006225586, "extraction_method": "TEXTRACT_SUMMARY"}, "buyer_gstin": {"page": null, "value": "36AABCA1234F1Z5", "source": "REGEX_FULLTEXT_ANCHORED", "confidence": 85, "extraction_method": "REGEX"}, "cgst_amount": {"page": null, "value": 12600, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "grand_total": {"page": 1, "value": "165,200.00", "source": "TEXTRACT_SUMMARY", "confidence": 99.92138671875, "extraction_method": "TEXTRACT_SUMMARY"}, "sgst_amount": {"page": null, "value": 12600, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "vendor_name": {"page": 1, "value": "Global Software Solutions Pvt. Ltd.", "source": "TEXTRACT_SUMMARY", "confidence": 98.18354034423828, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_date": {"page": 1, "value": "18-Aug-2026", "source": "TEXTRACT_SUMMARY", "confidence": 99.97993469238281, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_type": {"page": null, "value": "TAX_INVOICE", "source": "REGEX_FULLTEXT", "confidence": 80, "extraction_method": "REGEX"}, "vendor_gstin": {"page": 1, "value": "9924USA29003OSI", "source": "TEXTRACT_QUERY", "confidence": 98, "extraction_method": "TEXTRACT_QUERY"}, "buyer_address": {"page": 1, "value": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\nHyderabad, Telangana 500081\\n-\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36", "source": "TEXTRACT_SUMMARY", "confidence": 97.92948913574219, "extraction_method": "TEXTRACT_SUMMARY"}, "payment_terms": {"page": 1, "value": "Net 30 Days", "source": "TEXTRACT_SUMMARY", "confidence": 99.6680908203125, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_number": {"page": 1, "value": "INV-2026-00942", "source": "TEXTRACT_SUMMARY", "confidence": 98.63064575195312, "extraction_method": "TEXTRACT_SUMMARY"}, "reverse_charge": {"page": 1, "value": false, "source": "TEXTRACT_QUERY", "confidence": 75, "extraction_method": "TEXTRACT_QUERY"}, "taxable_amount": {"page": 1, "value": 140000, "source": "TEXTRACT_QUERY", "confidence": 94, "extraction_method": "TEXTRACT_QUERY"}, "vendor_address": {"page": 1, "value": "Global Software Solutions Pvt. Ltd.\\n5th Floor, Tech Park, Hitech City\\nHyderabad, Telangana 500081\\n-", "source": "TEXTRACT_SUMMARY", "confidence": 97.93276977539062, "extraction_method": "TEXTRACT_SUMMARY"}, "place_of_supply": {"page": 1, "value": "Telangana", "source": "TEXTRACT_QUERY", "confidence": 98, "extraction_method": "TEXTRACT_QUERY"}, "buyer_legal_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "source": "TEXTRACT_SUMMARY", "confidence": 99.79057312011719, "extraction_method": "TEXTRACT_SUMMARY"}, "vendor_legal_name": {"page": 1, "value": "Global Software Solutions Pvt. Ltd.", "source": "TEXTRACT_SUMMARY", "confidence": 98.18354034423828, "extraction_method": "TEXTRACT_SUMMARY"}, "buyer_shipping_address": {"page": 1, "value": "Apex Business Solutions Private Limited\\nPlot 18, Hitech City, Madhapur\\n-\\nHyderabad, Telangana 500081\\nGSTIN: 36AABCA1234F1Z5\\nState Code: 36", "source": "TEXTRACT_SUMMARY", "confidence": 98.21762084960938, "extraction_method": "TEXTRACT_SUMMARY"}}, "field_sources": {"hsn_sac": "REGEX_FULLTEXT", "due_date": "TEXTRACT_SUMMARY", "subtotal": "TEXTRACT_SUMMARY", "buyer_pan": "DERIVED_FROM_GSTIN", "cgst_rate": "REGEX_FULLTEXT", "po_number": "TEXTRACT_SUMMARY", "sgst_rate": "REGEX_FULLTEXT", "total_tax": "REGEX_FULLTEXT", "buyer_name": "TEXTRACT_SUMMARY", "buyer_gstin": "REGEX_FULLTEXT_ANCHORED", "cgst_amount": "REGEX_FULLTEXT", "grand_total": "TEXTRACT_SUMMARY", "sgst_amount": "REGEX_FULLTEXT", "vendor_name": "TEXTRACT_SUMMARY", "invoice_date": "TEXTRACT_SUMMARY", "invoice_type": "REGEX_FULLTEXT", "vendor_gstin": "TEXTRACT_QUERY", "buyer_address": "TEXTRACT_SUMMARY", "payment_terms": "TEXTRACT_SUMMARY", "invoice_number": "TEXTRACT_SUMMARY", "reverse_charge": "TEXTRACT_QUERY", "taxable_amount": "TEXTRACT_QUERY", "vendor_address": "TEXTRACT_SUMMARY", "place_of_supply": "TEXTRACT_QUERY", "buyer_legal_name": "TEXTRACT_SUMMARY", "vendor_legal_name": "TEXTRACT_SUMMARY", "buyer_shipping_address": "TEXTRACT_SUMMARY"}, "pages_processed": 1, "field_confidence": {"hsn_sac": 75.0, "due_date": 99.92374420166016, "subtotal": 99.98973846435547, "buyer_pan": 85.0, "cgst_rate": 75.0, "po_number": 99.95179748535156, "sgst_rate": 75.0, "total_tax": 75.0, "buyer_name": 99.9197006225586, "buyer_gstin": 85.0, "cgst_amount": 75.0, "grand_total": 99.92138671875, "sgst_amount": 75.0, "vendor_name": 98.18354034423828, "invoice_date": 99.97993469238281, "invoice_type": 80.0, "vendor_gstin": 98.0, "buyer_address": 97.92948913574219, "payment_terms": 99.6680908203125, "invoice_number": 98.63064575195312, "reverse_charge": 75.0, "taxable_amount": 94.0, "vendor_address": 97.93276977539062, "place_of_supply": 98.0, "buyer_legal_name": 99.79057312011719, "vendor_legal_name": 98.18354034423828, "buyer_shipping_address": 98.21762084960938}}, "raw_fields": {"query_results": {"IFSC": {"page": 1, "value": "997331", "confidence": 52}, "BUYER_GSTIN": {"page": 1, "value": "9924USA29003OSI", "confidence": 93}, "GRAND_TOTAL": {"page": 1, "value": "165,200.00", "confidence": 95}, "BANK_DETAILS": {"page": 1, "value": "9924USA29003OSI", "confidence": 90}, "SELLER_GSTIN": {"page": 1, "value": "9924USA29003OSI", "confidence": 98}, "PAYMENT_TERMS": {"page": 1, "value": "Net 30 Days", "confidence": 92}, "REVERSE_CHARGE": {"page": 1, "value": "No", "confidence": 75}, "TAXABLE_AMOUNT": {"page": 1, "value": "INR 1,40,000.00", "confidence": 94}, "PLACE_OF_SUPPLY": {"page": 1, "value": "Telangana", "confidence": 98}}}, "validation": {"issues": ["Vendor GSTIN '9924USA29003OSI' does not match the expected GSTIN structure."], "status": "REVIEW_REQUIRED", "is_valid": false, "warnings": [], "field_issues": [{"code": "INVALID_GSTIN_FORMAT", "field": "vendor_gstin", "message": "Vendor GSTIN '9924USA29003OSI' does not match the expected GSTIN structure."}], "tax_difference": 0.0, "total_difference": 0.0}, "invoice_lines": [{"unit": null, "hsn_sac": "997331", "discount": null, "quantity": 1.0, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": null, "unit_price": 100000.0, "cess_amount": null, "cgst_amount": null, "description": "Cloud ERP Software Subscription", "igst_amount": null, "line_number": 1, "sgst_amount": null, "ugst_amount": null, "product_code": "997331", "taxable_amount": null}, {"unit": null, "hsn_sac": "997331", "discount": null, "quantity": 1.0, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": null, "unit_price": 40000.0, "cess_amount": null, "cgst_amount": null, "description": "Implementation and Professional Services", "igst_amount": null, "line_number": 2, "sgst_amount": null, "ugst_amount": null, "product_code": "997331", "taxable_amount": null}]}	\N	\N	2026-08-24 05:42:48.505497
40	UPLOAD	\N	\N	\N	2026-08-25 13:50:54.346008	aws-gst-invoice-may-2026.pdf	invoices/2026/08/baf0ce1d31154dc8afce7634d91752c3_aws-gst-invoice-may-2026.pdf	EXTRACTED	91.96	{"tax": {"hsn_sac": "998315", "tax_type": "INTER_STATE_IGST", "cess_rate": null, "cgst_rate": null, "igst_rate": 18.0, "sgst_rate": null, "ugst_rate": null, "reverse_charge": false, "place_of_supply": "Telangana"}, "buyer": {"pan": null, "name": "Paves Global Infotech pvt ltd", "email": null, "gstin": null, "phone": null, "state": null, "address": "Paves Global Infotech pvt ltd\\nGachibowli\\nGachibowli\\nHyderabad, Telangana, 500032, IN", "country": null, "legal_name": "Paves Global Infotech pvt ltd", "state_code": null, "trade_name": null, "shipping_address": null}, "vendor": {"pan": "AAJCA9880A", "name": "Amazon Web Services India Private Limited", "email": null, "gstin": "07AAJCA9880A1ZL", "phone": null, "state": "Delhi", "address": "Amazon Web Services India Private Limited\\n(formerly known as Amazon Internet Services Private Limited)\\nBlock E, 14th Floor, Unit Nos. 1401 to 1421 International Trade Tower, Nehru Place,\\nNew Delhi, Delhi, 110019", "country": null, "website": null, "legal_name": "Amazon Web Services India Private Limited", "state_code": "07", "trade_name": null}, "amounts": {"discount": 8875.55, "subtotal": 3055.72, "round_off": null, "total_tax": 550.03, "tds_amount": null, "amount_paid": null, "balance_due": null, "cess_amount": null, "cgst_amount": null, "grand_total": 3605.75, "igst_amount": 550.03, "sgst_amount": null, "ugst_amount": null, "other_charges": null, "taxable_amount": null, "freight_charges": null, "handling_charges": null, "shipping_charges": null}, "payment": {"branch": null, "upi_id": null, "bank_name": null, "ifsc_code": null, "swift_code": null, "account_name": null, "payment_terms": null, "account_number": "743737183908"}, "document": {"currency": "INR", "due_date": null, "invoice_date": "2026-06-01", "invoice_type": "TAX_INVOICE", "document_type": "invoice", "invoice_number": "AIN2627000969471", "original_filename": "aws-gst-invoice-may-2026.pdf"}, "reference": {"po_date": null, "po_number": null, "order_number": null, "quotation_date": null, "contract_number": null, "quotation_number": null, "reference_number": null, "delivery_note_date": null, "delivery_note_number": null}, "compliance": {"irn": null, "qr_code_data": null, "export_invoice": null, "reverse_charge": false, "einvoice_status": null, "acknowledgement_date": null, "acknowledgement_number": null}, "extraction": {"job_id": "aee94f989fb4e7120d957a160689ea21ae13082c6eeb280aa0a51c97e17994f5", "status": "SUCCESS", "provider": "AWS_TEXTRACT", "warnings": [], "confidence": 91.964919090271, "field_details": {"hsn_sac": {"page": null, "value": "998315", "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "discount": {"page": 1, "value": "Rs. 8,875.55", "source": "TEXTRACT_SUMMARY", "confidence": 90.01663970947266, "extraction_method": "TEXTRACT_SUMMARY"}, "subtotal": {"page": 1, "value": "Rs. 3,055.72", "source": "TEXTRACT_SUMMARY", "confidence": 98.76010131835938, "extraction_method": "TEXTRACT_SUMMARY"}, "tax_type": {"page": null, "value": "INTER_STATE_IGST", "source": "DERIVED", "confidence": null, "extraction_method": "DERIVED"}, "igst_rate": {"page": null, "value": 18, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "total_tax": {"page": 1, "value": "Rs. 550.03", "source": "TEXTRACT_SUMMARY", "confidence": 92.52362823486328, "extraction_method": "TEXTRACT_SUMMARY"}, "buyer_name": {"page": 1, "value": "Paves Global Infotech pvt ltd", "source": "TEXTRACT_SUMMARY", "confidence": 99.868896484375, "extraction_method": "TEXTRACT_SUMMARY"}, "vendor_pan": {"page": null, "value": "AAJCA9880A", "source": "DERIVED_FROM_GSTIN", "confidence": 85, "extraction_method": "DERIVED"}, "grand_total": {"page": 1, "value": "Rs. 3,605.75", "source": "TEXTRACT_SUMMARY", "confidence": 97.93067932128906, "extraction_method": "TEXTRACT_SUMMARY"}, "igst_amount": {"page": null, "value": 550.03, "source": "REGEX_FULLTEXT", "confidence": 75, "extraction_method": "REGEX"}, "vendor_name": {"page": 1, "value": "Amazon Web Services India Private Limited", "source": "TEXTRACT_SUMMARY", "confidence": 99.90094757080078, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_date": {"page": 1, "value": "2026.06.01", "source": "TEXTRACT_SUMMARY", "confidence": 92.73100280761719, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_type": {"page": null, "value": "TAX_INVOICE", "source": "REGEX_FULLTEXT", "confidence": 80, "extraction_method": "REGEX"}, "vendor_gstin": {"page": null, "value": "07AAJCA9880A1ZL", "source": "REGEX_FULLTEXT_ANCHORED", "confidence": 85, "extraction_method": "REGEX"}, "buyer_address": {"page": 1, "value": "Paves Global Infotech pvt ltd\\nGachibowli\\nGachibowli\\nHyderabad, Telangana, 500032, IN", "source": "TEXTRACT_SUMMARY", "confidence": 99.31129455566406, "extraction_method": "TEXTRACT_SUMMARY"}, "account_number": {"page": 1, "value": "743737183908", "source": "TEXTRACT_SUMMARY", "confidence": 99.9194107055664, "extraction_method": "TEXTRACT_SUMMARY"}, "billing_period": {"page": 1, "value": "May 1 - May 31, 2026", "source": "TEXTRACT_QUERY", "confidence": 92, "extraction_method": "TEXTRACT_QUERY"}, "invoice_number": {"page": 1, "value": "AIN2627000969471", "source": "TEXTRACT_SUMMARY", "confidence": 98.3331298828125, "extraction_method": "TEXTRACT_SUMMARY"}, "reverse_charge": {"page": 1, "value": false, "source": "TEXTRACT_QUERY", "confidence": 61, "extraction_method": "TEXTRACT_QUERY"}, "vendor_address": {"page": 1, "value": "Amazon Web Services India Private Limited\\n(formerly known as Amazon Internet Services Private Limited)\\nBlock E, 14th Floor, Unit Nos. 1401 to 1421 International Trade Tower, Nehru Place,\\nNew Delhi, Delhi, 110019", "source": "TEXTRACT_SUMMARY", "confidence": 99.02031707763672, "extraction_method": "TEXTRACT_SUMMARY"}, "place_of_supply": {"page": 1, "value": "Telangana", "source": "TEXTRACT_QUERY", "confidence": 99, "extraction_method": "TEXTRACT_QUERY"}, "buyer_legal_name": {"page": 1, "value": "Paves Global Infotech pvt ltd", "source": "DERIVED_FROM_NAME", "confidence": 99.868896484375, "extraction_method": "DERIVED"}, "vendor_legal_name": {"page": 1, "value": "Amazon Web Services India Private Limited", "source": "DERIVED_FROM_NAME", "confidence": 99.90094757080078, "extraction_method": "DERIVED"}}, "field_sources": {"hsn_sac": "REGEX_FULLTEXT", "discount": "TEXTRACT_SUMMARY", "subtotal": "TEXTRACT_SUMMARY", "igst_rate": "REGEX_FULLTEXT", "total_tax": "TEXTRACT_SUMMARY", "buyer_name": "TEXTRACT_SUMMARY", "vendor_pan": "DERIVED_FROM_GSTIN", "grand_total": "TEXTRACT_SUMMARY", "igst_amount": "REGEX_FULLTEXT", "vendor_name": "TEXTRACT_SUMMARY", "invoice_date": "TEXTRACT_SUMMARY", "invoice_type": "REGEX_FULLTEXT", "vendor_gstin": "REGEX_FULLTEXT_ANCHORED", "buyer_address": "TEXTRACT_SUMMARY", "account_number": "TEXTRACT_SUMMARY", "billing_period": "TEXTRACT_QUERY", "invoice_number": "TEXTRACT_SUMMARY", "reverse_charge": "TEXTRACT_QUERY", "vendor_address": "TEXTRACT_SUMMARY", "place_of_supply": "TEXTRACT_QUERY", "buyer_legal_name": "DERIVED_FROM_NAME", "vendor_legal_name": "DERIVED_FROM_NAME"}, "pages_processed": 3, "field_confidence": {"hsn_sac": 75.0, "discount": 90.01663970947266, "subtotal": 98.76010131835938, "igst_rate": 75.0, "total_tax": 92.52362823486328, "buyer_name": 99.868896484375, "vendor_pan": 85.0, "grand_total": 97.93067932128906, "igst_amount": 75.0, "vendor_name": 99.90094757080078, "invoice_date": 92.73100280761719, "invoice_type": 80.0, "vendor_gstin": 85.0, "buyer_address": 99.31129455566406, "account_number": 99.9194107055664, "billing_period": 92.0, "invoice_number": 98.3331298828125, "reverse_charge": 61.0, "vendor_address": 99.02031707763672, "place_of_supply": 99.0, "buyer_legal_name": 99.868896484375, "vendor_legal_name": 99.90094757080078}}, "raw_fields": {"query_results": {"BILLING_PERIOD": {"page": 1, "value": "May 1 - May 31, 2026", "confidence": 92}, "REVERSE_CHARGE": {"page": 1, "value": "No", "confidence": 61}, "PLACE_OF_SUPPLY": {"page": 1, "value": "Telangana", "confidence": 99}}}, "validation": {"issues": [], "status": "READY_FOR_VALIDATION", "is_valid": true, "warnings": ["Buyer GSTIN could not be confidently extracted."], "field_issues": [{"code": "MISSING_FIELD", "field": "buyer_gstin", "message": "Buyer GSTIN could not be confidently extracted."}], "tax_difference": 0.0, "total_difference": 0.0}, "invoice_lines": [{"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 3605.75, "unit_price": 3605.75, "cess_amount": null, "cgst_amount": null, "description": null, "igst_amount": null, "line_number": 1, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 0.0, "unit_price": 0.0, "cess_amount": null, "cgst_amount": null, "description": "Credits/Discount", "igst_amount": null, "line_number": 2, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 503.26, "unit_price": 503.26, "cess_amount": null, "cgst_amount": null, "description": "Amazon Relational Database Service", "igst_amount": null, "line_number": 3, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 19.05, "unit_price": 19.05, "cess_amount": null, "cgst_amount": null, "description": "AWS Systems Manager", "igst_amount": null, "line_number": 4, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 314.96, "unit_price": 314.96, "cess_amount": null, "cgst_amount": null, "description": "AWS Secrets Manager", "igst_amount": null, "line_number": 5, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 0.0, "unit_price": 0.0, "cess_amount": null, "cgst_amount": null, "description": "Amazon Elastic Compute Cloud", "igst_amount": null, "line_number": 6, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 11.21, "unit_price": 11.21, "cess_amount": null, "cgst_amount": null, "description": "Amazon EC2 Container Registry (ECR)", "igst_amount": null, "line_number": 7, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 112.08, "unit_price": 112.08, "cess_amount": null, "cgst_amount": null, "description": "AWS Key Management Service", "igst_amount": null, "line_number": 8, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 2644.07, "unit_price": 2644.07, "cess_amount": null, "cgst_amount": null, "description": "Amazon Virtual Private Cloud", "igst_amount": null, "line_number": 9, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}]}	15	13	2026-08-25 13:50:54.346008
41	UPLOAD	\N	\N	\N	2026-08-26 06:01:42.907651	aws-gst-invoice-may-2026.pdf	invoices/2026/08/757a182d6de548b99629338cfffcb5db_aws-gst-invoice-may-2026.pdf	EXTRACTED	\N	\N	15	13	2026-08-26 06:01:42.907651
42	UPLOAD	\N	\N	\N	2026-08-26 06:06:04.419561	keka_gst_invoice_text_pdf.pdf	invoices/2026/08/82e8b09044ba4973b060c99144613e54_keka_gst_invoice_text_pdf.pdf	EXTRACTED	54.15	{"cess": null, "cgst": "12600.00", "igst": null, "sgst": "165200.00", "gstin": null, "lines": [{"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": null, "unit_price": "1", "description": "HR & Employee Experience Software", "line_amount": "100000.00", "line_number": 1}, {"quantity": null, "tax_rate": null, "tax_type": null, "confidence": 0.75, "tax_amount": null, "unit_price": "1", "description": "Implementation and Professional", "line_amount": "40000.00", "line_number": 2}], "total": "165200.00", "currency": "INR", "due_date": "2026-09-10", "subtotal": "140000.00", "tax_rate": null, "tax_type": null, "po_number": "PO-45001234", "tax_amount": null, "buyer_gstin": "36AAFCK5835K1Z6", "vendor_name": "Apex Business Solutions Private Limited", "invoice_date": "2026-08-11", "payment_terms": "Net 30 Days", "field_metadata": {"cess": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "cgst": {"page": 1, "value": "12600.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "CGST"}, "igst": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "sgst": {"page": 1, "value": "165200.00", "method": "ANCHOR+BELOW+GEOMETRY", "confidence": 58.0, "matched_anchor": "SGST"}, "gstin": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "total": {"page": 1, "value": "165200.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "Grand Total"}, "currency": {"page": 1, "value": "INR", "method": "GEOMETRY+NEAREST", "confidence": 30.0, "matched_anchor": null}, "due_date": {"page": 1, "value": "2026-09-10", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Due Date"}, "subtotal": {"page": 1, "value": "140000.00", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Subtotal"}, "tax_rate": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "tax_type": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "po_number": {"page": 1, "value": "PO-45001234", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "PO Number"}, "tax_amount": {"page": null, "value": null, "method": "NONE", "confidence": 0.0, "matched_anchor": null}, "buyer_gstin": {"page": 1, "value": "36AAFCK5835K1Z6", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 95.0, "matched_anchor": "GSTIN"}, "vendor_name": {"page": 1, "value": "Apex Business Solutions Private Limited", "method": "FALLBACK+GEOMETRY", "confidence": 43.0, "matched_anchor": null}, "invoice_date": {"page": 1, "value": "2026-08-11", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Invoice Date"}, "payment_terms": {"page": 1, "value": "Net 30 Days", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 75.0, "matched_anchor": "Payment Terms"}, "invoice_number": {"page": 1, "value": "INV-2026-00871", "method": "ANCHOR+GEOMETRY+SAME_LINE", "confidence": 55.0, "matched_anchor": "Invoice No."}}, "invoice_number": "INV-2026-00871", "field_confidences": {"cess": 0.0, "cgst": 75.0, "igst": 0.0, "sgst": 58.0, "gstin": 0.0, "total": 95.0, "currency": 30.0, "due_date": 55.0, "subtotal": 75.0, "tax_rate": 0.0, "tax_type": 0.0, "po_number": 55.0, "tax_amount": 0.0, "buyer_gstin": 95.0, "vendor_name": 43.0, "invoice_date": 55.0, "payment_terms": 75.0, "invoice_number": 55.0}}	16	14	2026-08-26 06:06:04.419561
\.


--
-- Data for Name: invoice; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice (invoice_id, invoice_number, vendor_id, inbound_document_id, invoice_type, po_id, grn_id, invoice_date, due_date, payment_term_id, currency_id, gross_amount, discount_amount, tax_amount, net_amount, amount_paid, status_id, created_by, created_at, updated_by, updated_at) FROM stdin;
13	AIN2627000969471	15	40	NON_PO	\N	\N	2026-06-01	2026-06-01	\N	1	3605.75	8875.55	550.03	3605.75	0.00	6	1	2026-08-25 13:50:54.346008	1	2026-08-25 13:50:54.346008
14	INV-2026-00871	16	42	PO	\N	\N	2026-08-11	2026-09-10	\N	1	140000.00	0.00	177800.00	165200.00	0.00	6	1	2026-08-26 06:06:04.559567	1	2026-08-26 06:06:04.559567
\.


--
-- Data for Name: invoice_approval; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice_approval (invoice_approval_id, invoice_id, invoice_issue_id, approver_name, decision, comments, decided_at, created_at) FROM stdin;
\.


--
-- Data for Name: invoice_attachment; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice_attachment (invoice_attachment_id, invoice_id, file_name, file_path, uploaded_at) FROM stdin;
13	13	aws-gst-invoice-may-2026.pdf	invoices/2026/08/baf0ce1d31154dc8afce7634d91752c3_aws-gst-invoice-may-2026.pdf	2026-08-25 13:50:54.346008
14	14	keka_gst_invoice_text_pdf.pdf	invoices/2026/08/82e8b09044ba4973b060c99144613e54_keka_gst_invoice_text_pdf.pdf	2026-08-26 06:06:04.559567
\.


--
-- Data for Name: invoice_issue; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice_issue (invoice_issue_id, invoice_id, issue_source, issue_type, severity, result, description, status_id, resolved_by, resolved_at, created_at) FROM stdin;
5	14	EXTRACTION	LOW_OCR_CONFIDENCE	WARNING	\N	Overall extraction confidence 54.1 is below the 80.0 review threshold	\N	\N	\N	2026-08-26 06:06:04.559567
6	14	VALIDATION	VALIDATION_FAILED	WARNING	\N	GSTIN is required; Total 165200.00 does not match subtotal + taxes 317800.00 (tolerance 1.00)	\N	\N	\N	2026-08-26 06:06:04.559567
\.


--
-- Data for Name: invoice_line; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice_line (invoice_line_id, invoice_id, line_number, description, quantity, unit_price, line_amount, tax_type_id, tax_amount, po_line_id) FROM stdin;
36	13	1		1.0000	3605.7500	3605.75	\N	0.00	\N
37	13	2	Credits/Discount	1.0000	0.0000	0.00	\N	0.00	\N
38	13	3	Amazon Relational Database Service	1.0000	503.2600	503.26	\N	0.00	\N
39	13	4	AWS Systems Manager	1.0000	19.0500	19.05	\N	0.00	\N
40	13	5	AWS Secrets Manager	1.0000	314.9600	314.96	\N	0.00	\N
41	13	6	Amazon Elastic Compute Cloud	1.0000	0.0000	0.00	\N	0.00	\N
42	13	7	Amazon EC2 Container Registry (ECR)	1.0000	11.2100	11.21	\N	0.00	\N
43	13	8	AWS Key Management Service	1.0000	112.0800	112.08	\N	0.00	\N
44	13	9	Amazon Virtual Private Cloud	1.0000	2644.0700	2644.07	\N	0.00	\N
45	14	1	HR & Employee Experience Software	1.0000	1.0000	100000.00	\N	0.00	\N
46	14	2	Implementation and Professional	1.0000	1.0000	40000.00	\N	0.00	\N
\.


--
-- Data for Name: payment; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.payment (payment_id, vendor_id, vendor_bank_id, scheduled_date, payment_date, total_amount, currency_id, payment_method, reference_number, status_id, created_by, created_at, updated_by, updated_at) FROM stdin;
\.


--
-- Data for Name: payment_invoice; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.payment_invoice (payment_invoice_id, payment_id, invoice_id, allocated_amount, created_at) FROM stdin;
\.


--
-- Data for Name: payment_term; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.payment_term (payment_term_id, term_name, due_days, discount_percent, discount_days, is_system_default, is_active, created_by, created_at, updated_by, updated_at) FROM stdin;
1	Immediate	0	0.00	0	t	t	\N	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
2	Net 15	15	0.00	0	t	t	\N	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
3	Net 30	30	2.00	10	t	t	\N	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
4	Net 45	45	0.00	0	t	t	\N	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
5	Net 60	60	0.00	0	t	t	\N	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
\.


--
-- Data for Name: purchase_category; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.purchase_category (id, code, name, description, is_active, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: purchase_order; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.purchase_order (id, po_number, pr_id, quotation_id, vendor_id, po_date, expected_delivery_date, delivery_location, payment_terms, delivery_terms, subtotal, tax_amount, total_amount, status_id, created_by, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: purchase_order_line; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.purchase_order_line (id, po_id, pr_line_id, item_name, description, quantity, uom, unit_price, tax_rate, tax_amount, total_amount, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: purchase_requisition; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.purchase_requisition (id, pr_number, department_id, purchase_category_id, status_id, priority, required_by, delivery_location, justification, estimated_total, selected_vendor_id, selected_quotation_id, approved_by, approved_at, approval_comment, created_by, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: purchase_requisition_line; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.purchase_requisition_line (id, pr_id, item_name, description, quantity, uom, estimated_unit_price, estimated_amount, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: quotation; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.quotation (id, quotation_number, pr_id, vendor_id, quotation_date, valid_until, total_amount, file_url, status_id, created_by, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: status_master; Type: TABLE DATA; Schema: ap; Owner: -
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
24	PURCHASE_REQUISITION	DRAFT	Draft	1
25	PURCHASE_REQUISITION	PENDING_APPROVAL	Pending Approval	2
26	PURCHASE_REQUISITION	APPROVED	Approved	3
27	PURCHASE_REQUISITION	VENDOR_SELECTION	Vendor Selection	4
28	PURCHASE_REQUISITION	PO_GENERATED	PO Generated	5
29	PURCHASE_REQUISITION	REJECTED	Rejected	6
30	PURCHASE_REQUISITION	CANCELLED	Cancelled	7
31	QUOTATION	RECEIVED	Received	1
32	QUOTATION	SELECTED	Selected	2
33	QUOTATION	REJECTED	Rejected	3
\.


--
-- Data for Name: system_configuration; Type: TABLE DATA; Schema: ap; Owner: -
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
-- Data for Name: tax_rate_rule; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.tax_rate_rule (tax_rate_rule_id, tax_rule_id, rate_percent, calculation_type, fixed_amount, effective_from, effective_to, is_active, created_by, created_at, updated_by, updated_at) FROM stdin;
1	1	18.0000	PERCENTAGE	\N	2026-04-01	\N	t	\N	2026-08-19 09:43:30.461288	\N	2026-08-19 09:43:30.461288
2	2	18.0000	PERCENTAGE	\N	2026-04-01	\N	t	\N	2026-08-19 09:44:25.883772	\N	2026-08-19 09:44:25.883772
3	3	9.0000	PERCENTAGE	\N	2026-04-01	\N	t	\N	2026-08-19 09:44:54.850562	\N	2026-08-19 09:44:54.850562
4	4	9.0000	PERCENTAGE	\N	2026-04-01	\N	t	\N	2026-08-19 09:45:20.547435	\N	2026-08-19 09:45:20.547435
5	5	18.0000	PERCENTAGE	\N	2026-04-01	\N	t	\N	2026-08-19 09:45:33.778154	\N	2026-08-19 09:45:33.778154
6	6	1.0000	PERCENTAGE	\N	2026-04-01	\N	t	\N	2026-08-21 14:29:39.049266	\N	2026-08-21 14:29:39.049266
7	7	10.0000	PERCENTAGE	\N	2026-04-01	\N	t	\N	2026-08-21 14:29:39.049266	\N	2026-08-21 14:29:39.049266
8	8	10.0000	PERCENTAGE	\N	2026-04-01	\N	t	\N	2026-08-21 14:29:39.049266	\N	2026-08-21 14:29:39.049266
9	9	2.0000	PERCENTAGE	\N	2026-04-01	\N	t	\N	2026-08-21 14:29:39.049266	\N	2026-08-21 14:29:39.049266
10	10	0.1000	PERCENTAGE	\N	2026-04-01	\N	t	\N	2026-08-21 14:29:39.049266	\N	2026-08-21 14:29:39.049266
\.


--
-- Data for Name: tax_rule; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.tax_rule (tax_rule_id, rule_code, rule_name, tax_type_id, rule_category, description, priority, effective_from, effective_to, is_active, created_by, created_at, updated_by, updated_at) FROM stdin;
1	GST_SAC_997331	GST for SAC 997331	1	GST_RATE	GST rate applicable for SAC 997331	100	2026-04-01	\N	t	\N	2026-08-19 09:36:53.714444	\N	2026-08-19 09:36:53.714444
2	GST_SAC_998315	GST for SAC 998315	1	GST_RATE	GST rate applicable for SAC 998315	100	2026-04-01	\N	t	\N	2026-08-19 09:44:02.557072	\N	2026-08-19 09:44:02.557072
3	CGST_9_SAME_STATE	CGST 9% - Intra State	5	TAX_COMPONENT	CGST applies when supplier and buyer are in the same state for applicable 18% GST supplies	100	2026-04-01	\N	t	\N	2026-08-19 09:44:44.779867	\N	2026-08-19 09:44:44.779867
4	SGST_9_SAME_STATE	SGST 9% - Intra State	6	TAX_COMPONENT	SGST applies when supplier and buyer are in the same state for applicable 18% GST supplies	100	2026-04-01	\N	t	\N	2026-08-19 09:45:20.547435	\N	2026-08-19 09:45:20.547435
5	IGST_18_DIFFERENT_STATE	IGST 18% - Inter State	7	TAX_COMPONENT	IGST applies when supplier and buyer are in different states for applicable 18% GST supplies	100	2026-04-01	\N	t	\N	2026-08-19 09:45:33.778154	\N	2026-08-19 09:45:33.778154
6	TDS_194C	TDS - Contractor Payments	2	TDS_RATE	TDS applicable on payments to contractors/sub-contractors under Section 194C	100	2026-04-01	\N	t	\N	2026-08-21 14:29:27.17909	\N	2026-08-21 14:29:27.17909
7	TDS_194J	TDS - Professional or Technical Services	2	TDS_RATE	TDS applicable on professional or technical service payments under Section 194J	100	2026-04-01	\N	t	\N	2026-08-21 14:29:27.17909	\N	2026-08-21 14:29:27.17909
8	TDS_194I	TDS - Rent	2	TDS_RATE	TDS applicable on specified rent payments under Section 194I	100	2026-04-01	\N	t	\N	2026-08-21 14:29:27.17909	\N	2026-08-21 14:29:27.17909
9	TDS_194H	TDS - Commission or Brokerage	2	TDS_RATE	TDS applicable on commission or brokerage payments under Section 194H	100	2026-04-01	\N	t	\N	2026-08-21 14:29:27.17909	\N	2026-08-21 14:29:27.17909
10	TDS_194Q	TDS - Purchase of Goods	2	TDS_RATE	TDS applicable on specified purchases of goods under Section 194Q	100	2026-04-01	\N	t	\N	2026-08-21 14:29:27.17909	\N	2026-08-21 14:29:27.17909
\.


--
-- Data for Name: tax_rule_condition; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.tax_rule_condition (tax_rule_condition_id, tax_rule_id, condition_type, operator, condition_value, logical_group, sequence_no, created_at, updated_at) FROM stdin;
1	1	SAC	EQUALS	997331	1	1	2026-08-19 09:43:39.755398	2026-08-19 09:43:39.755398
2	2	SAC	EQUALS	998315	1	1	2026-08-19 09:44:36.11968	2026-08-19 09:44:36.11968
3	3	SUPPLY_LOCATION	SAME_STATE	TRUE	1	1	2026-08-19 09:45:09.866046	2026-08-19 09:45:09.866046
4	4	SUPPLY_LOCATION	SAME_STATE	TRUE	1	1	2026-08-19 09:45:20.547435	2026-08-19 09:45:20.547435
5	5	SUPPLY_LOCATION	DIFFERENT_STATE	TRUE	1	1	2026-08-19 09:45:33.778154	2026-08-19 09:45:33.778154
6	6	PAYMENT_NATURE	EQUALS	CONTRACTOR	1	1	2026-08-21 14:29:49.786576	2026-08-21 14:29:49.786576
7	7	PAYMENT_NATURE	EQUALS	PROFESSIONAL_SERVICE	1	1	2026-08-21 14:29:49.786576	2026-08-21 14:29:49.786576
8	8	PAYMENT_NATURE	EQUALS	RENT	1	1	2026-08-21 14:29:49.786576	2026-08-21 14:29:49.786576
9	9	PAYMENT_NATURE	EQUALS	COMMISSION	1	1	2026-08-21 14:29:49.786576	2026-08-21 14:29:49.786576
10	10	PAYMENT_NATURE	EQUALS	PURCHASE_OF_GOODS	1	1	2026-08-21 14:29:49.786576	2026-08-21 14:29:49.786576
\.


--
-- Data for Name: tax_type; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.tax_type (tax_type_id, country_id, tax_name, tax_code, is_withholding, is_system_default, is_active, created_by, created_at, updated_by, updated_at) FROM stdin;
3	3	Standard VAT	VAT-STD	f	t	t	1	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
4	2	Sales Tax	SALES-TX	f	t	t	1	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
1	1	GST	GST	f	t	t	1	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
2	1	TDS	TDS	t	t	t	1	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
5	1	CGST	CGST	f	t	t	\N	2026-08-14 04:52:57.208759	\N	2026-08-14 04:52:57.208759
6	1	SGST	SGST	f	t	t	\N	2026-08-14 04:52:57.208759	\N	2026-08-14 04:52:57.208759
7	1	IGST	IGST	f	t	t	\N	2026-08-14 04:52:57.208759	\N	2026-08-14 04:52:57.208759
\.


--
-- Data for Name: vendor; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor (vendor_id, vendor_name, vendor_code, country_id, payment_term_id, currency_id, phone_number, email, status_id, created_by, created_at, updated_by, updated_at, pan_number) FROM stdin;
15	AMAZON WEB SERVICES INDIA PRIVATE LIMITED	AWSIPL0336	1	2	1	9100633230	support.aws@example.com	2	5100031	2026-08-10 16:33:37.113797	5100031	2026-08-10 16:33:37.113797	AAJCA9880A
16	KEKA TECHNOLOGIES PRIVATE LIMITED	KTPL1020	1	\N	1	9122541230	admin.keka@keka.com	2	5100031	2026-08-11 13:40:20.883477	5100031	2026-08-11 13:40:20.883477	AAFCK5835K
\.


--
-- Data for Name: vendor_address; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor_address (vendor_address_id, vendor_id, address_type, address_line1, address_line2, city, state, postal_code, country_id, is_primary, created_at, updated_at) FROM stdin;
11	15	REGISTERED	Block E	International Trade Tower, South Delhi	NEHRU PLACE	Delhi	110019	1	t	2026-08-10 16:33:37.822493	2026-08-10 16:33:37.822493
12	16	REGISTERED	Survey no. 17 Vasavi Shalom Sky City	Gachibowli, Rangareddy	Hyderabad	Telangana	500032	1	t	2026-08-11 13:40:21.482888	2026-08-11 13:40:21.482888
\.


--
-- Data for Name: vendor_bank; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor_bank (vendor_bank_id, vendor_id, bank_name, account_holder_name, account_number, iban, swift_code, routing_number, ifsc_code, is_primary, effective_from, effective_to, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: vendor_category; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor_category (vendor_category_id, category_code, category_name, parent_category_id, description, is_active, created_by, created_at, updated_by, updated_at) FROM stdin;
1	IT_TECH	IT & Technology	\N	Technology-related products and services	t	\N	2026-08-31 10:03:42.864302	\N	2026-08-31 10:03:42.864302
2	PROF_SERV	Professional Services	\N	Professional and business services	t	\N	2026-08-31 10:03:42.864302	\N	2026-08-31 10:03:42.864302
3	FAC_ADMIN	Facilities & Administration	\N	Facilities and administrative services	t	\N	2026-08-31 10:03:42.864302	\N	2026-08-31 10:03:42.864302
4	TRAVEL_LOG	Travel & Logistics	\N	Travel, transportation and logistics	t	\N	2026-08-31 10:03:42.864302	\N	2026-08-31 10:03:42.864302
5	MARKETING	Marketing	\N	Marketing, advertising and promotional services	t	\N	2026-08-31 10:03:42.864302	\N	2026-08-31 10:03:42.864302
6	HR_SERV	HR & Employee Services	\N	Human resources and employee-related services	t	\N	2026-08-31 10:03:42.864302	\N	2026-08-31 10:03:42.864302
7	FIN_SERV	Financial Services	\N	Financial and related services	t	\N	2026-08-31 10:03:42.864302	\N	2026-08-31 10:03:42.864302
8	CLOUD	Cloud Services	1	Cloud infrastructure and cloud computing services	t	\N	2026-08-31 10:04:14.351111	\N	2026-08-31 10:04:14.351111
9	SOFTWARE_SAAS	Software & SaaS	1	Software products and SaaS subscriptions	t	\N	2026-08-31 10:04:14.351111	\N	2026-08-31 10:04:14.351111
10	IT_HARDWARE	IT Hardware	1	Computers, laptops, monitors and other IT equipment	t	\N	2026-08-31 10:04:14.351111	\N	2026-08-31 10:04:14.351111
11	IT_SUPPORT	IT Support	1	IT support and maintenance services	t	\N	2026-08-31 10:04:14.351111	\N	2026-08-31 10:04:14.351111
\.


--
-- Data for Name: vendor_category_mapping; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor_category_mapping (vendor_category_mapping_id, vendor_id, vendor_category_id, is_primary, created_by, created_at, updated_by, updated_at) FROM stdin;
1	15	8	t	5100031	2026-08-31 10:04:29.583807	\N	2026-08-31 10:04:29.583807
2	16	9	t	5100031	2026-08-31 10:04:39.759911	\N	2026-08-31 10:04:39.759911
\.


--
-- Data for Name: vendor_tax; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor_tax (vendor_tax_id, registration_type, registration_number, is_verified, verified_at, created_at, vendor_address_id) FROM stdin;
10	GST	07AAJCA9880A1ZL	t	\N	2026-08-10 16:33:38.28736	11
11	GST	36AAFCK5835K1Z6	t	\N	2026-08-11 13:40:21.934612	12
\.


--
-- Name: audit_log_audit_log_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.audit_log_audit_log_id_seq', 96, true);


--
-- Name: country_country_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.country_country_id_seq', 6, true);


--
-- Name: currency_currency_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.currency_currency_id_seq', 3, true);


--
-- Name: department_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.department_id_seq', 1, false);


--
-- Name: goods_receipt_grn_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.goods_receipt_grn_id_seq', 12, true);


--
-- Name: goods_receipt_line_grn_line_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.goods_receipt_line_grn_line_id_seq', 16, true);


--
-- Name: inbound_document_inbound_document_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.inbound_document_inbound_document_id_seq', 42, true);


--
-- Name: invoice_approval_invoice_approval_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.invoice_approval_invoice_approval_id_seq', 1, true);


--
-- Name: invoice_attachment_invoice_attachment_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.invoice_attachment_invoice_attachment_id_seq', 14, true);


--
-- Name: invoice_invoice_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.invoice_invoice_id_seq', 14, true);


--
-- Name: invoice_issue_invoice_issue_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.invoice_issue_invoice_issue_id_seq', 6, true);


--
-- Name: invoice_line_invoice_line_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.invoice_line_invoice_line_id_seq', 46, true);


--
-- Name: payment_invoice_payment_invoice_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.payment_invoice_payment_invoice_id_seq', 1, false);


--
-- Name: payment_payment_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.payment_payment_id_seq', 1, false);


--
-- Name: payment_term_payment_term_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.payment_term_payment_term_id_seq', 5, true);


--
-- Name: purchase_category_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.purchase_category_id_seq', 1, false);


--
-- Name: purchase_order_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.purchase_order_id_seq', 1, false);


--
-- Name: purchase_order_line_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.purchase_order_line_id_seq', 1, false);


--
-- Name: purchase_requisition_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.purchase_requisition_id_seq', 1, false);


--
-- Name: purchase_requisition_line_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.purchase_requisition_line_id_seq', 1, false);


--
-- Name: quotation_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.quotation_id_seq', 1, false);


--
-- Name: status_master_status_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.status_master_status_id_seq', 33, true);


--
-- Name: tax_rate_rule_tax_rate_rule_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.tax_rate_rule_tax_rate_rule_id_seq', 10, true);


--
-- Name: tax_rule_condition_tax_rule_condition_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.tax_rule_condition_tax_rule_condition_id_seq', 10, true);


--
-- Name: tax_rule_tax_rule_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.tax_rule_tax_rule_id_seq', 10, true);


--
-- Name: tax_type_tax_type_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.tax_type_tax_type_id_seq', 7, true);


--
-- Name: vendor_address_vendor_address_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.vendor_address_vendor_address_id_seq', 12, true);


--
-- Name: vendor_bank_vendor_bank_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.vendor_bank_vendor_bank_id_seq', 7, true);


--
-- Name: vendor_category_mapping_vendor_category_mapping_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.vendor_category_mapping_vendor_category_mapping_id_seq', 2, true);


--
-- Name: vendor_category_vendor_category_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.vendor_category_vendor_category_id_seq', 11, true);


--
-- Name: vendor_tax_vendor_tax_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.vendor_tax_vendor_tax_id_seq', 11, true);


--
-- Name: vendor_vendor_id_seq; Type: SEQUENCE SET; Schema: ap; Owner: -
--

SELECT pg_catalog.setval('ap.vendor_vendor_id_seq', 16, true);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (audit_log_id);


--
-- Name: country country_country_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.country
    ADD CONSTRAINT country_country_code_key UNIQUE (country_code);


--
-- Name: country country_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.country
    ADD CONSTRAINT country_pkey PRIMARY KEY (country_id);


--
-- Name: currency currency_currency_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.currency
    ADD CONSTRAINT currency_currency_code_key UNIQUE (currency_code);


--
-- Name: currency currency_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.currency
    ADD CONSTRAINT currency_pkey PRIMARY KEY (currency_id);


--
-- Name: department department_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.department
    ADD CONSTRAINT department_code_key UNIQUE (code);


--
-- Name: department department_name_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.department
    ADD CONSTRAINT department_name_key UNIQUE (name);


--
-- Name: department department_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.department
    ADD CONSTRAINT department_pkey PRIMARY KEY (id);


--
-- Name: department_purchase_category department_purchase_category_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.department_purchase_category
    ADD CONSTRAINT department_purchase_category_pkey PRIMARY KEY (department_id, purchase_category_id);


--
-- Name: goods_receipt_line goods_receipt_line_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.goods_receipt_line
    ADD CONSTRAINT goods_receipt_line_pkey PRIMARY KEY (grn_line_id);


--
-- Name: goods_receipt goods_receipt_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.goods_receipt
    ADD CONSTRAINT goods_receipt_pkey PRIMARY KEY (grn_id);


--
-- Name: inbound_document inbound_document_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.inbound_document
    ADD CONSTRAINT inbound_document_pkey PRIMARY KEY (inbound_document_id);


--
-- Name: invoice_approval invoice_approval_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval
    ADD CONSTRAINT invoice_approval_pkey PRIMARY KEY (invoice_approval_id);


--
-- Name: invoice_attachment invoice_attachment_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_attachment
    ADD CONSTRAINT invoice_attachment_pkey PRIMARY KEY (invoice_attachment_id);


--
-- Name: invoice_issue invoice_issue_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_issue
    ADD CONSTRAINT invoice_issue_pkey PRIMARY KEY (invoice_issue_id);


--
-- Name: invoice_line invoice_line_invoice_id_line_number_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_line
    ADD CONSTRAINT invoice_line_invoice_id_line_number_key UNIQUE (invoice_id, line_number);


--
-- Name: invoice_line invoice_line_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_line
    ADD CONSTRAINT invoice_line_pkey PRIMARY KEY (invoice_line_id);


--
-- Name: invoice invoice_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_pkey PRIMARY KEY (invoice_id);


--
-- Name: invoice invoice_vendor_id_invoice_number_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_vendor_id_invoice_number_key UNIQUE (vendor_id, invoice_number);


--
-- Name: payment_invoice payment_invoice_payment_id_invoice_id_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment_invoice
    ADD CONSTRAINT payment_invoice_payment_id_invoice_id_key UNIQUE (payment_id, invoice_id);


--
-- Name: payment_invoice payment_invoice_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment_invoice
    ADD CONSTRAINT payment_invoice_pkey PRIMARY KEY (payment_invoice_id);


--
-- Name: payment payment_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment
    ADD CONSTRAINT payment_pkey PRIMARY KEY (payment_id);


--
-- Name: payment_term payment_term_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment_term
    ADD CONSTRAINT payment_term_pkey PRIMARY KEY (payment_term_id);


--
-- Name: payment_term payment_term_term_name_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment_term
    ADD CONSTRAINT payment_term_term_name_key UNIQUE (term_name);


--
-- Name: purchase_category purchase_category_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_category
    ADD CONSTRAINT purchase_category_code_key UNIQUE (code);


--
-- Name: purchase_category purchase_category_name_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_category
    ADD CONSTRAINT purchase_category_name_key UNIQUE (name);


--
-- Name: purchase_category purchase_category_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_category
    ADD CONSTRAINT purchase_category_pkey PRIMARY KEY (id);


--
-- Name: purchase_order_line purchase_order_line_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_order_line
    ADD CONSTRAINT purchase_order_line_pkey PRIMARY KEY (id);


--
-- Name: purchase_order purchase_order_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_order
    ADD CONSTRAINT purchase_order_pkey PRIMARY KEY (id);


--
-- Name: purchase_order purchase_order_po_number_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_order
    ADD CONSTRAINT purchase_order_po_number_key UNIQUE (po_number);


--
-- Name: purchase_requisition_line purchase_requisition_line_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_requisition_line
    ADD CONSTRAINT purchase_requisition_line_pkey PRIMARY KEY (id);


--
-- Name: purchase_requisition purchase_requisition_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_requisition
    ADD CONSTRAINT purchase_requisition_pkey PRIMARY KEY (id);


--
-- Name: purchase_requisition purchase_requisition_pr_number_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_requisition
    ADD CONSTRAINT purchase_requisition_pr_number_key UNIQUE (pr_number);


--
-- Name: quotation quotation_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.quotation
    ADD CONSTRAINT quotation_pkey PRIMARY KEY (id);


--
-- Name: status_master status_master_module_name_status_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.status_master
    ADD CONSTRAINT status_master_module_name_status_code_key UNIQUE (module_name, status_code);


--
-- Name: status_master status_master_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.status_master
    ADD CONSTRAINT status_master_pkey PRIMARY KEY (status_id);


--
-- Name: system_configuration system_configuration_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.system_configuration
    ADD CONSTRAINT system_configuration_pkey PRIMARY KEY (config_key);


--
-- Name: tax_rate_rule tax_rate_rule_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_rate_rule
    ADD CONSTRAINT tax_rate_rule_pkey PRIMARY KEY (tax_rate_rule_id);


--
-- Name: tax_rule_condition tax_rule_condition_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_rule_condition
    ADD CONSTRAINT tax_rule_condition_pkey PRIMARY KEY (tax_rule_condition_id);


--
-- Name: tax_rule tax_rule_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_rule
    ADD CONSTRAINT tax_rule_pkey PRIMARY KEY (tax_rule_id);


--
-- Name: tax_rule tax_rule_rule_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_rule
    ADD CONSTRAINT tax_rule_rule_code_key UNIQUE (rule_code);


--
-- Name: tax_type tax_type_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_type
    ADD CONSTRAINT tax_type_pkey PRIMARY KEY (tax_type_id);


--
-- Name: vendor_address vendor_address_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_address
    ADD CONSTRAINT vendor_address_pkey PRIMARY KEY (vendor_address_id);


--
-- Name: vendor_bank vendor_bank_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_bank
    ADD CONSTRAINT vendor_bank_pkey PRIMARY KEY (vendor_bank_id);


--
-- Name: vendor_category vendor_category_category_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category
    ADD CONSTRAINT vendor_category_category_code_key UNIQUE (category_code);


--
-- Name: vendor_category_mapping vendor_category_mapping_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping
    ADD CONSTRAINT vendor_category_mapping_pkey PRIMARY KEY (vendor_category_mapping_id);


--
-- Name: vendor_category_mapping vendor_category_mapping_unique; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping
    ADD CONSTRAINT vendor_category_mapping_unique UNIQUE (vendor_id, vendor_category_id);


--
-- Name: vendor_category vendor_category_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category
    ADD CONSTRAINT vendor_category_pkey PRIMARY KEY (vendor_category_id);


--
-- Name: vendor vendor_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_pkey PRIMARY KEY (vendor_id);


--
-- Name: vendor_tax vendor_tax_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_tax
    ADD CONSTRAINT vendor_tax_pkey PRIMARY KEY (vendor_tax_id);


--
-- Name: vendor vendor_vendor_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_vendor_code_key UNIQUE (vendor_code);


--
-- Name: idx_audit_new_values; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_audit_new_values ON ap.audit_log USING gin (new_values);


--
-- Name: idx_audit_table_record; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_audit_table_record ON ap.audit_log USING btree (table_name, record_id);


--
-- Name: idx_grn_line_grn; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_grn_line_grn ON ap.goods_receipt_line USING btree (grn_id);


--
-- Name: idx_grn_line_po_line; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_grn_line_po_line ON ap.goods_receipt_line USING btree (po_line_id);


--
-- Name: idx_grn_po; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_grn_po ON ap.goods_receipt USING btree (po_id);


--
-- Name: idx_grn_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_grn_vendor ON ap.goods_receipt USING btree (vendor_id);


--
-- Name: idx_inbound_document_message_id; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_inbound_document_message_id ON ap.inbound_document USING btree (email_message_id);


--
-- Name: idx_inbound_document_raw_data; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_inbound_document_raw_data ON ap.inbound_document USING gin (raw_extracted_data);


--
-- Name: idx_inbound_document_status; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_inbound_document_status ON ap.inbound_document USING btree (extraction_status);


--
-- Name: idx_invoice_approval_invoice; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_invoice_approval_invoice ON ap.invoice_approval USING btree (invoice_id);


--
-- Name: idx_invoice_due_date; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_invoice_due_date ON ap.invoice USING btree (due_date);


--
-- Name: idx_invoice_issue_invoice; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_invoice_issue_invoice ON ap.invoice_issue USING btree (invoice_id);


--
-- Name: idx_invoice_issue_severity; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_invoice_issue_severity ON ap.invoice_issue USING btree (severity);


--
-- Name: idx_invoice_line_po_line; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_invoice_line_po_line ON ap.invoice_line USING btree (po_line_id);


--
-- Name: idx_invoice_po; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_invoice_po ON ap.invoice USING btree (po_id);


--
-- Name: idx_invoice_status; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_invoice_status ON ap.invoice USING btree (status_id);


--
-- Name: idx_invoice_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_invoice_vendor ON ap.invoice USING btree (vendor_id);


--
-- Name: idx_payment_invoice_invoice; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_payment_invoice_invoice ON ap.payment_invoice USING btree (invoice_id);


--
-- Name: idx_payment_invoice_payment; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_payment_invoice_payment ON ap.payment_invoice USING btree (payment_id);


--
-- Name: idx_payment_scheduled_date; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_payment_scheduled_date ON ap.payment USING btree (scheduled_date);


--
-- Name: idx_payment_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_payment_vendor ON ap.payment USING btree (vendor_id);


--
-- Name: idx_po_line_po; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_po_line_po ON ap.purchase_order_line USING btree (po_id);


--
-- Name: idx_po_line_pr_line; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_po_line_pr_line ON ap.purchase_order_line USING btree (pr_line_id);


--
-- Name: idx_po_pr; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_po_pr ON ap.purchase_order USING btree (pr_id);


--
-- Name: idx_po_quotation; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_po_quotation ON ap.purchase_order USING btree (quotation_id);


--
-- Name: idx_po_status; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_po_status ON ap.purchase_order USING btree (status_id);


--
-- Name: idx_po_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_po_vendor ON ap.purchase_order USING btree (vendor_id);


--
-- Name: idx_pr_category; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_pr_category ON ap.purchase_requisition USING btree (purchase_category_id);


--
-- Name: idx_pr_created_by; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_pr_created_by ON ap.purchase_requisition USING btree (created_by);


--
-- Name: idx_pr_department; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_pr_department ON ap.purchase_requisition USING btree (department_id);


--
-- Name: idx_pr_line_pr; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_pr_line_pr ON ap.purchase_requisition_line USING btree (pr_id);


--
-- Name: idx_pr_selected_quotation; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_pr_selected_quotation ON ap.purchase_requisition USING btree (selected_quotation_id);


--
-- Name: idx_pr_selected_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_pr_selected_vendor ON ap.purchase_requisition USING btree (selected_vendor_id);


--
-- Name: idx_pr_status; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_pr_status ON ap.purchase_requisition USING btree (status_id);


--
-- Name: idx_quotation_pr; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_quotation_pr ON ap.quotation USING btree (pr_id);


--
-- Name: idx_quotation_status; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_quotation_status ON ap.quotation USING btree (status_id);


--
-- Name: idx_quotation_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_quotation_vendor ON ap.quotation USING btree (vendor_id);


--
-- Name: idx_vendor_address_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_address_vendor ON ap.vendor_address USING btree (vendor_id);


--
-- Name: idx_vendor_bank_active; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_bank_active ON ap.vendor_bank USING btree (vendor_id, effective_to);


--
-- Name: idx_vendor_bank_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_bank_vendor ON ap.vendor_bank USING btree (vendor_id);


--
-- Name: idx_vendor_country; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_country ON ap.vendor USING btree (country_id);


--
-- Name: idx_vendor_email; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_email ON ap.vendor USING btree (email);


--
-- Name: idx_vendor_status; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_status ON ap.vendor USING btree (status_id);


--
-- Name: department_purchase_category fk_dpc_department; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.department_purchase_category
    ADD CONSTRAINT fk_dpc_department FOREIGN KEY (department_id) REFERENCES ap.department(id) ON DELETE CASCADE;


--
-- Name: department_purchase_category fk_dpc_purchase_category; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.department_purchase_category
    ADD CONSTRAINT fk_dpc_purchase_category FOREIGN KEY (purchase_category_id) REFERENCES ap.purchase_category(id) ON DELETE CASCADE;


--
-- Name: goods_receipt fk_goods_receipt_po; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.goods_receipt
    ADD CONSTRAINT fk_goods_receipt_po FOREIGN KEY (po_id) REFERENCES ap.purchase_order(id);


--
-- Name: inbound_document fk_inbound_document_invoice; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.inbound_document
    ADD CONSTRAINT fk_inbound_document_invoice FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id);


--
-- Name: purchase_order_line fk_po_line_po; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_order_line
    ADD CONSTRAINT fk_po_line_po FOREIGN KEY (po_id) REFERENCES ap.purchase_order(id) ON DELETE CASCADE;


--
-- Name: purchase_order_line fk_po_line_pr_line; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_order_line
    ADD CONSTRAINT fk_po_line_pr_line FOREIGN KEY (pr_line_id) REFERENCES ap.purchase_requisition_line(id);


--
-- Name: purchase_order fk_po_pr; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_order
    ADD CONSTRAINT fk_po_pr FOREIGN KEY (pr_id) REFERENCES ap.purchase_requisition(id);


--
-- Name: purchase_order fk_po_quotation; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_order
    ADD CONSTRAINT fk_po_quotation FOREIGN KEY (quotation_id) REFERENCES ap.quotation(id);


--
-- Name: purchase_order fk_po_status; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_order
    ADD CONSTRAINT fk_po_status FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: purchase_order fk_po_vendor; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_order
    ADD CONSTRAINT fk_po_vendor FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: purchase_requisition fk_pr_department; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_requisition
    ADD CONSTRAINT fk_pr_department FOREIGN KEY (department_id) REFERENCES ap.department(id);


--
-- Name: purchase_requisition_line fk_pr_line_pr; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_requisition_line
    ADD CONSTRAINT fk_pr_line_pr FOREIGN KEY (pr_id) REFERENCES ap.purchase_requisition(id) ON DELETE CASCADE;


--
-- Name: purchase_requisition fk_pr_purchase_category; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_requisition
    ADD CONSTRAINT fk_pr_purchase_category FOREIGN KEY (purchase_category_id) REFERENCES ap.purchase_category(id);


--
-- Name: purchase_requisition fk_pr_selected_quotation; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_requisition
    ADD CONSTRAINT fk_pr_selected_quotation FOREIGN KEY (selected_quotation_id) REFERENCES ap.quotation(id);


--
-- Name: purchase_requisition fk_pr_status; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_requisition
    ADD CONSTRAINT fk_pr_status FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: purchase_requisition fk_pr_vendor; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_requisition
    ADD CONSTRAINT fk_pr_vendor FOREIGN KEY (selected_vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: quotation fk_quotation_pr; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.quotation
    ADD CONSTRAINT fk_quotation_pr FOREIGN KEY (pr_id) REFERENCES ap.purchase_requisition(id) ON DELETE CASCADE;


--
-- Name: quotation fk_quotation_status; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.quotation
    ADD CONSTRAINT fk_quotation_status FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: quotation fk_quotation_vendor; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.quotation
    ADD CONSTRAINT fk_quotation_vendor FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: goods_receipt_line goods_receipt_line_grn_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.goods_receipt_line
    ADD CONSTRAINT goods_receipt_line_grn_id_fkey FOREIGN KEY (grn_id) REFERENCES ap.goods_receipt(grn_id) ON DELETE CASCADE;


--
-- Name: goods_receipt goods_receipt_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.goods_receipt
    ADD CONSTRAINT goods_receipt_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: inbound_document inbound_document_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.inbound_document
    ADD CONSTRAINT inbound_document_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: invoice_approval invoice_approval_invoice_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval
    ADD CONSTRAINT invoice_approval_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id) ON DELETE CASCADE;


--
-- Name: invoice_approval invoice_approval_invoice_issue_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval
    ADD CONSTRAINT invoice_approval_invoice_issue_id_fkey FOREIGN KEY (invoice_issue_id) REFERENCES ap.invoice_issue(invoice_issue_id);


--
-- Name: invoice_attachment invoice_attachment_invoice_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_attachment
    ADD CONSTRAINT invoice_attachment_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id) ON DELETE CASCADE;


--
-- Name: invoice invoice_currency_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES ap.currency(currency_id);


--
-- Name: invoice invoice_grn_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_grn_id_fkey FOREIGN KEY (grn_id) REFERENCES ap.goods_receipt(grn_id);


--
-- Name: invoice invoice_inbound_document_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_inbound_document_id_fkey FOREIGN KEY (inbound_document_id) REFERENCES ap.inbound_document(inbound_document_id);


--
-- Name: invoice_issue invoice_issue_invoice_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_issue
    ADD CONSTRAINT invoice_issue_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id) ON DELETE CASCADE;


--
-- Name: invoice_issue invoice_issue_status_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_issue
    ADD CONSTRAINT invoice_issue_status_id_fkey FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: invoice_line invoice_line_invoice_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_line
    ADD CONSTRAINT invoice_line_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id) ON DELETE CASCADE;


--
-- Name: invoice_line invoice_line_tax_type_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_line
    ADD CONSTRAINT invoice_line_tax_type_id_fkey FOREIGN KEY (tax_type_id) REFERENCES ap.tax_type(tax_type_id);


--
-- Name: invoice invoice_payment_term_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_payment_term_id_fkey FOREIGN KEY (payment_term_id) REFERENCES ap.payment_term(payment_term_id);


--
-- Name: invoice invoice_status_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_status_id_fkey FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: invoice invoice_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: payment payment_currency_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment
    ADD CONSTRAINT payment_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES ap.currency(currency_id);


--
-- Name: payment_invoice payment_invoice_invoice_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment_invoice
    ADD CONSTRAINT payment_invoice_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id);


--
-- Name: payment_invoice payment_invoice_payment_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment_invoice
    ADD CONSTRAINT payment_invoice_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES ap.payment(payment_id) ON DELETE CASCADE;


--
-- Name: payment payment_status_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment
    ADD CONSTRAINT payment_status_id_fkey FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: payment payment_vendor_bank_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment
    ADD CONSTRAINT payment_vendor_bank_id_fkey FOREIGN KEY (vendor_bank_id) REFERENCES ap.vendor_bank(vendor_bank_id);


--
-- Name: payment payment_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.payment
    ADD CONSTRAINT payment_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: tax_rate_rule tax_rate_rule_tax_rule_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_rate_rule
    ADD CONSTRAINT tax_rate_rule_tax_rule_id_fkey FOREIGN KEY (tax_rule_id) REFERENCES ap.tax_rule(tax_rule_id) ON DELETE CASCADE;


--
-- Name: tax_rule_condition tax_rule_condition_tax_rule_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_rule_condition
    ADD CONSTRAINT tax_rule_condition_tax_rule_id_fkey FOREIGN KEY (tax_rule_id) REFERENCES ap.tax_rule(tax_rule_id) ON DELETE CASCADE;


--
-- Name: tax_rule tax_rule_tax_type_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_rule
    ADD CONSTRAINT tax_rule_tax_type_id_fkey FOREIGN KEY (tax_type_id) REFERENCES ap.tax_type(tax_type_id);


--
-- Name: tax_type tax_type_country_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_type
    ADD CONSTRAINT tax_type_country_id_fkey FOREIGN KEY (country_id) REFERENCES ap.country(country_id);


--
-- Name: vendor_address vendor_address_country_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_address
    ADD CONSTRAINT vendor_address_country_id_fkey FOREIGN KEY (country_id) REFERENCES ap.country(country_id);


--
-- Name: vendor_address vendor_address_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_address
    ADD CONSTRAINT vendor_address_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id) ON DELETE CASCADE;


--
-- Name: vendor_bank vendor_bank_vendor_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_bank
    ADD CONSTRAINT vendor_bank_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id) ON DELETE CASCADE;


--
-- Name: vendor_category_mapping vendor_category_mapping_category_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping
    ADD CONSTRAINT vendor_category_mapping_category_fk FOREIGN KEY (vendor_category_id) REFERENCES ap.vendor_category(vendor_category_id);


--
-- Name: vendor_category_mapping vendor_category_mapping_vendor_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping
    ADD CONSTRAINT vendor_category_mapping_vendor_fk FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: vendor_category vendor_category_parent_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category
    ADD CONSTRAINT vendor_category_parent_fk FOREIGN KEY (parent_category_id) REFERENCES ap.vendor_category(vendor_category_id);


--
-- Name: vendor vendor_country_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_country_id_fkey FOREIGN KEY (country_id) REFERENCES ap.country(country_id);


--
-- Name: vendor vendor_currency_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES ap.currency(currency_id);


--
-- Name: vendor vendor_payment_term_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_payment_term_id_fkey FOREIGN KEY (payment_term_id) REFERENCES ap.payment_term(payment_term_id);


--
-- Name: vendor vendor_status_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_status_id_fkey FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: vendor_tax vendor_tax_vendor_address_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_tax
    ADD CONSTRAINT vendor_tax_vendor_address_id_fkey FOREIGN KEY (vendor_address_id) REFERENCES ap.vendor_address(vendor_address_id);


--
-- PostgreSQL database dump complete
--

\unrestrict ROJpVzdXNx6uIrfufmS11Ovye9cVWYZR8YMw74pBVJtl0SFspn00osLriFtMC39

