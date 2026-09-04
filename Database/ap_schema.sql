--
-- Database/ap_schema.sql
-- PostgreSQL database dump
--

\restrict 24blkwLEGiYZghsaGi1qs0OVVumsInAu5k8PK5TYRG3LAhGUItbP56ikK57BfvX

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

\unrestrict 24blkwLEGiYZghsaGi1qs0OVVumsInAu5k8PK5TYRG3LAhGUItbP56ikK57BfvX

