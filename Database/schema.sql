--
-- PostgreSQL database dump
--


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


--
-- Name: update_modified_column(); Type: FUNCTION; Schema: ap; Owner: -
--

CREATE FUNCTION ap.update_modified_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: approval_policy; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.approval_policy (
    id bigint NOT NULL,
    name character varying(150) NOT NULL,
    department_id bigint,
    purchase_category_id bigint,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    description character varying(500),
    min_amount numeric(18,2),
    max_amount numeric(18,2),
    is_default boolean DEFAULT false NOT NULL,
    CONSTRAINT chk_approval_policy_amount_range CHECK (((min_amount IS NULL) OR (max_amount IS NULL) OR (min_amount <= max_amount)))
);


--
-- Name: approval_policy_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.approval_policy_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: approval_policy_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.approval_policy_id_seq OWNED BY ap.approval_policy.id;


--
-- Name: approval_policy_level; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.approval_policy_level (
    id bigint NOT NULL,
    approval_policy_id bigint NOT NULL,
    level_number integer NOT NULL,
    approver_type character varying(30) NOT NULL,
    approval_rule character varying(20) DEFAULT 'ANY_ONE'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    role_code character varying(50),
    user_uuid uuid,
    CONSTRAINT chk_approval_policy_level_approval_rule CHECK (((approval_rule)::text = ANY ((ARRAY['ANY_ONE'::character varying, 'ALL'::character varying])::text[]))),
    CONSTRAINT chk_approval_policy_level_approver_type CHECK (((approver_type)::text = ANY ((ARRAY['DEPARTMENT_APPROVER'::character varying, 'ROLE'::character varying, 'USER'::character varying])::text[])))
);


--
-- Name: approval_policy_level_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.approval_policy_level_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: approval_policy_level_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.approval_policy_level_id_seq OWNED BY ap.approval_policy_level.id;


--
-- Name: approver_directory; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.approver_directory (
    id bigint NOT NULL,
    user_uuid uuid NOT NULL,
    employee_uuid uuid NOT NULL,
    department_uuid uuid,
    is_user_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    department_name character varying(255)
);


--
-- Name: approver_directory_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.approver_directory_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: approver_directory_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.approver_directory_id_seq OWNED BY ap.approver_directory.id;


--
-- Name: approver_directory_role; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.approver_directory_role (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_uuid uuid NOT NULL,
    role_id integer NOT NULL,
    role_code character varying(50) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: audit_log; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.audit_log (
    audit_log_id bigint NOT NULL,
    table_name character varying(50) NOT NULL,
    record_id integer NOT NULL,
    action character varying(50) NOT NULL,
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
-- Name: cdc_failure_log; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.cdc_failure_log (
    id bigint NOT NULL,
    kafka_topic character varying(255) NOT NULL,
    kafka_partition integer NOT NULL,
    kafka_offset bigint NOT NULL,
    entity_type character varying(50) NOT NULL,
    entity_key character varying(255),
    operation character varying(20),
    failure_type character varying(50) NOT NULL,
    error_message text,
    raw_payload jsonb,
    retry_count integer DEFAULT 0 NOT NULL,
    max_retries integer DEFAULT 5 NOT NULL,
    status character varying(20) DEFAULT 'FAILED'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cdc_failure_log_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.cdc_failure_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cdc_failure_log_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.cdc_failure_log_id_seq OWNED BY ap.cdc_failure_log.id;


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
-- Name: department_approver; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.department_approver (
    id bigint NOT NULL,
    department_id bigint NOT NULL,
    user_uuid uuid NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by character varying(100)
);


--
-- Name: department_approver_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.department_approver_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: department_approver_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.department_approver_id_seq OWNED BY ap.department_approver.id;


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
-- Name: eos_department_cache; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.eos_department_cache (
    department_uuid uuid NOT NULL,
    department_name character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    raw_payload jsonb,
    source_ts_ms bigint,
    synced_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: eos_employee_cache; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.eos_employee_cache (
    employee_uuid uuid NOT NULL,
    department_uuid uuid,
    is_active boolean DEFAULT true NOT NULL,
    raw_payload jsonb,
    source_ts_ms bigint,
    synced_at timestamp with time zone DEFAULT now() NOT NULL
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
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    department_id bigint,
    purchase_category_id bigint
);


--
-- Name: invoice_approval; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.invoice_approval (
    invoice_approval_id integer NOT NULL,
    invoice_id integer NOT NULL,
    approval_policy_id bigint NOT NULL,
    status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    invoice_issue_id integer,
    completed_at timestamp with time zone,
    CONSTRAINT chk_invoice_approval_status CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'IN_PROGRESS'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying, 'CANCELLED'::character varying])::text[])))
);


--
-- Name: invoice_approval_legacy; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.invoice_approval_legacy (
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

ALTER SEQUENCE ap.invoice_approval_invoice_approval_id_seq OWNED BY ap.invoice_approval_legacy.invoice_approval_id;


--
-- Name: invoice_approval_invoice_approval_id_seq1; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.invoice_approval_invoice_approval_id_seq1
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: invoice_approval_invoice_approval_id_seq1; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.invoice_approval_invoice_approval_id_seq1 OWNED BY ap.invoice_approval.invoice_approval_id;


--
-- Name: invoice_approval_step; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.invoice_approval_step (
    id bigint NOT NULL,
    invoice_approval_id integer NOT NULL,
    level_number integer NOT NULL,
    approver_type character varying(30) NOT NULL,
    approval_rule character varying(20) NOT NULL,
    status character varying(20) DEFAULT 'WAITING'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    role_code character varying(50),
    department_id bigint,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    CONSTRAINT chk_invoice_approval_step_approval_rule CHECK (((approval_rule)::text = ANY ((ARRAY['ANY_ONE'::character varying, 'ALL'::character varying])::text[]))),
    CONSTRAINT chk_invoice_approval_step_approver_type CHECK (((approver_type)::text = ANY ((ARRAY['DEPARTMENT_APPROVER'::character varying, 'ROLE'::character varying, 'USER'::character varying])::text[]))),
    CONSTRAINT chk_invoice_approval_step_status CHECK (((status)::text = ANY ((ARRAY['WAITING'::character varying, 'PENDING'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying, 'SKIPPED'::character varying, 'CANCELLED'::character varying])::text[])))
);


--
-- Name: invoice_approval_step_approver; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.invoice_approval_step_approver (
    id bigint NOT NULL,
    approval_step_id bigint NOT NULL,
    user_uuid uuid NOT NULL,
    status character varying(20) DEFAULT 'WAITING'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    decided_at timestamp with time zone,
    comments character varying(500),
    CONSTRAINT chk_invoice_approval_step_approver_status CHECK (((status)::text = ANY ((ARRAY['WAITING'::character varying, 'PENDING'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying, 'SKIPPED'::character varying])::text[])))
);


--
-- Name: invoice_approval_step_approver_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.invoice_approval_step_approver_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: invoice_approval_step_approver_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.invoice_approval_step_approver_id_seq OWNED BY ap.invoice_approval_step_approver.id;


--
-- Name: invoice_approval_step_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.invoice_approval_step_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: invoice_approval_step_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.invoice_approval_step_id_seq OWNED BY ap.invoice_approval_step.id;


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
-- Name: invoice_tds; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.invoice_tds (
    id integer NOT NULL,
    invoice_id integer NOT NULL,
    tds_applicable boolean DEFAULT false NOT NULL,
    payment_nature_id integer,
    tds_rule_id integer,
    tds_rate_rule_id integer,
    taxable_base numeric(18,2),
    tds_rate numeric(7,4),
    tds_amount numeric(18,2),
    threshold_amount numeric(18,2),
    prior_period_aggregate numeric(18,2) DEFAULT 0,
    current_transaction_amount numeric(18,2),
    aggregate_amount numeric(18,2),
    pan_status character varying(30),
    entity_type character varying(50),
    determination_status character varying(30) DEFAULT 'PENDING'::character varying NOT NULL,
    determination_reason text,
    determined_at timestamp without time zone,
    determined_by character varying(100),
    verified_at timestamp without time zone,
    verified_by character varying(100),
    remarks text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    gstin_status character varying(30),
    gstin_checked_at timestamp without time zone,
    CONSTRAINT invoice_tds_amount_chk CHECK (((tds_amount IS NULL) OR (tds_amount >= (0)::numeric))),
    CONSTRAINT invoice_tds_amounts_chk CHECK (((taxable_base IS NULL) OR (taxable_base >= (0)::numeric))),
    CONSTRAINT invoice_tds_determination_status_chk CHECK (((determination_status)::text = ANY ((ARRAY['PENDING'::character varying, 'DETERMINED'::character varying, 'VERIFIED'::character varying])::text[]))),
    CONSTRAINT invoice_tds_rate_chk CHECK (((tds_rate IS NULL) OR (tds_rate >= (0)::numeric)))
);


--
-- Name: invoice_tds_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

ALTER TABLE ap.invoice_tds ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME ap.invoice_tds_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: nda_template; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.nda_template (
    id bigint NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(150) NOT NULL,
    version character varying(20) NOT NULL,
    body text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    created_by character varying(100),
    updated_by character varying(100)
);


--
-- Name: nda_template_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.nda_template_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nda_template_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.nda_template_id_seq OWNED BY ap.nda_template.id;


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
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    department_id bigint NOT NULL
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
-- Name: purchase_category_tds_mapping; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.purchase_category_tds_mapping (
    id integer NOT NULL,
    purchase_category_id integer NOT NULL,
    tds_payment_nature_id integer NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: purchase_category_tds_mapping_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

ALTER TABLE ap.purchase_category_tds_mapping ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME ap.purchase_category_tds_mapping_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


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
    sourcing_type character varying(20),
    selection_reason text,
    CONSTRAINT chk_pr_estimated_total CHECK ((estimated_total >= (0)::numeric)),
    CONSTRAINT chk_pr_priority CHECK (((priority)::text = ANY ((ARRAY['LOW'::character varying, 'NORMAL'::character varying, 'HIGH'::character varying, 'URGENT'::character varying])::text[]))),
    CONSTRAINT chk_pr_sourcing_type CHECK (((sourcing_type IS NULL) OR ((sourcing_type)::text = ANY ((ARRAY['CATALOG'::character varying, 'RFQ'::character varying])::text[]))))
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
    is_custom_uom boolean DEFAULT false NOT NULL,
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
    rfq_id bigint,
    delivery_days integer,
    payment_terms character varying(100),
    CONSTRAINT chk_quotation_delivery_days CHECK (((delivery_days IS NULL) OR (delivery_days >= 0))),
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
-- Name: rfq; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.rfq (
    id bigint NOT NULL,
    rfq_number character varying(50) NOT NULL,
    pr_id bigint NOT NULL,
    status_id bigint NOT NULL,
    created_by character varying(100) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    due_date date,
    sent_at timestamp with time zone,
    closed_by character varying(100),
    closed_at timestamp with time zone
);


--
-- Name: rfq_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.rfq_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rfq_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.rfq_id_seq OWNED BY ap.rfq.id;


--
-- Name: rfq_vendor; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.rfq_vendor (
    id bigint NOT NULL,
    rfq_id bigint NOT NULL,
    vendor_id bigint NOT NULL,
    invited_by character varying(100) NOT NULL,
    invited_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: rfq_vendor_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.rfq_vendor_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rfq_vendor_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.rfq_vendor_id_seq OWNED BY ap.rfq_vendor.id;


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
    legal_reference character varying(50),
    threshold_amount numeric(18,2),
    threshold_type character varying(20),
    CONSTRAINT tax_rule_effective_dates_chk CHECK (((effective_to IS NULL) OR (effective_to >= effective_from))),
    CONSTRAINT tax_rule_threshold_amount_chk CHECK (((threshold_amount IS NULL) OR (threshold_amount >= (0)::numeric))),
    CONSTRAINT tax_rule_threshold_type_chk CHECK (((threshold_type IS NULL) OR ((threshold_type)::text = ANY ((ARRAY['PER_TRANSACTION'::character varying, 'AGGREGATE_PERIOD'::character varying])::text[]))))
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
-- Name: tds_payment_nature; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.tds_payment_nature (
    id integer NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(150) NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: tds_payment_nature_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

ALTER TABLE ap.tds_payment_nature ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME ap.tds_payment_nature_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: ums_role_cache; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.ums_role_cache (
    role_id integer NOT NULL,
    role_name character varying(150),
    raw_payload jsonb,
    source_ts_ms bigint,
    synced_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ums_role_cache_role_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.ums_role_cache_role_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ums_role_cache_role_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.ums_role_cache_role_id_seq OWNED BY ap.ums_role_cache.role_id;


--
-- Name: ums_user_cache; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.ums_user_cache (
    user_id integer NOT NULL,
    user_uuid uuid NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    raw_payload jsonb,
    source_ts_ms bigint,
    synced_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ums_user_cache_user_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.ums_user_cache_user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ums_user_cache_user_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.ums_user_cache_user_id_seq OWNED BY ap.ums_user_cache.user_id;


--
-- Name: unit_of_measure; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.unit_of_measure (
    id integer NOT NULL,
    code character varying(20) NOT NULL,
    name character varying(100) NOT NULL,
    category character varying(30) NOT NULL,
    allows_decimal boolean DEFAULT true NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


--
-- Name: unit_of_measure_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.unit_of_measure_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: unit_of_measure_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.unit_of_measure_id_seq OWNED BY ap.unit_of_measure.id;


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
    department_id bigint NOT NULL,
    purchase_category_id bigint NOT NULL,
    is_primary boolean DEFAULT false NOT NULL,
    pre_screen_status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    business_requirement text,
    purpose_of_onboarding text,
    pre_screen_result_reason text,
    pre_screen_checked_at timestamp without time zone,
    nda_recommended boolean,
    nda_override boolean,
    nda_override_reason text,
    nda_final_required boolean,
    nda_decided_by character varying(100),
    nda_decided_at timestamp without time zone,
    created_by character varying(100),
    updated_by character varying(100),
    CONSTRAINT chk_vendor_engagement_pre_screen_status CHECK (((pre_screen_status)::text = ANY ((ARRAY['PENDING'::character varying, 'PASS'::character varying, 'NEED_INFORMATION'::character varying, 'FAIL'::character varying])::text[])))
);


--
-- Name: vendor_category_mapping_legacy; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.vendor_category_mapping_legacy (
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
-- Name: vendor_category_mapping_legacy_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

ALTER TABLE ap.vendor_category_mapping_legacy ALTER COLUMN vendor_category_mapping_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME ap.vendor_category_mapping_legacy_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: vendor_category_mapping_vendor_category_mapping_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.vendor_category_mapping_vendor_category_mapping_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: vendor_category_mapping_vendor_category_mapping_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.vendor_category_mapping_vendor_category_mapping_id_seq OWNED BY ap.vendor_category_mapping.vendor_category_mapping_id;


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
-- Name: vendor_nda; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.vendor_nda (
    nda_id bigint NOT NULL,
    vendor_id integer NOT NULL,
    nda_required boolean DEFAULT true NOT NULL,
    nda_status_id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    pr_id bigint,
    department_id bigint,
    purchase_category_id bigint,
    template_id bigint,
    template_version character varying(20),
    document_key character varying(500),
    signed_document_key character varying(500),
    recipient_email character varying(150),
    valid_from date,
    valid_until date,
    sent_at timestamp without time zone,
    signed_at timestamp without time zone,
    completed_at timestamp without time zone,
    created_by character varying(100),
    updated_by character varying(100),
    content_version integer DEFAULT 1 NOT NULL,
    content_updated_at timestamp without time zone,
    content_updated_by character varying(100),
    content text
);


--
-- Name: vendor_nda_nda_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.vendor_nda_nda_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: vendor_nda_nda_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.vendor_nda_nda_id_seq OWNED BY ap.vendor_nda.nda_id;


--
-- Name: vendor_onboarding_request; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.vendor_onboarding_request (
    id bigint NOT NULL,
    pr_id bigint NOT NULL,
    department_id bigint NOT NULL,
    purchase_category_id bigint NOT NULL,
    status_id integer NOT NULL,
    created_by character varying(100) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    business_requirement text,
    purpose_of_onboarding text,
    requested_vendor_name character varying(200),
    requested_vendor_email character varying(150),
    vendor_id integer,
    engagement_id integer,
    assigned_to character varying(100),
    closed_at timestamp without time zone,
    updated_by character varying(100)
);


--
-- Name: vendor_onboarding_request_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.vendor_onboarding_request_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: vendor_onboarding_request_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.vendor_onboarding_request_id_seq OWNED BY ap.vendor_onboarding_request.id;


--
-- Name: vendor_screening_rule; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.vendor_screening_rule (
    id bigint NOT NULL,
    name character varying(150) NOT NULL,
    requires_nda boolean DEFAULT false NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    department_id bigint,
    purchase_category_id bigint,
    description text,
    created_by character varying(100),
    updated_by character varying(100)
);


--
-- Name: vendor_screening_rule_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

CREATE SEQUENCE ap.vendor_screening_rule_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: vendor_screening_rule_id_seq; Type: SEQUENCE OWNED BY; Schema: ap; Owner: -
--

ALTER SEQUENCE ap.vendor_screening_rule_id_seq OWNED BY ap.vendor_screening_rule.id;


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
    vendor_address_id integer NOT NULL
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
-- Name: vendor_tds_profile; Type: TABLE; Schema: ap; Owner: -
--

CREATE TABLE ap.vendor_tds_profile (
    id integer NOT NULL,
    vendor_id integer NOT NULL,
    entity_type character varying(50),
    residency_type character varying(30) DEFAULT 'RESIDENT'::character varying NOT NULL,
    pan_status character varying(30) DEFAULT 'VALID'::character varying NOT NULL,
    lower_deduction_available boolean DEFAULT false NOT NULL,
    certificate_number character varying(100),
    certificate_rate numeric(7,4),
    certificate_valid_from date,
    certificate_valid_to date,
    tds_exemption_flag boolean DEFAULT false NOT NULL,
    exemption_reason character varying(500),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT vendor_tds_certificate_dates_chk CHECK (((certificate_valid_to IS NULL) OR (certificate_valid_from IS NULL) OR (certificate_valid_to >= certificate_valid_from))),
    CONSTRAINT vendor_tds_certificate_rate_chk CHECK (((certificate_rate IS NULL) OR (certificate_rate >= (0)::numeric)))
);


--
-- Name: vendor_tds_profile_id_seq; Type: SEQUENCE; Schema: ap; Owner: -
--

ALTER TABLE ap.vendor_tds_profile ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME ap.vendor_tds_profile_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


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
-- Name: approval_policy id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approval_policy ALTER COLUMN id SET DEFAULT nextval('ap.approval_policy_id_seq'::regclass);


--
-- Name: approval_policy_level id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approval_policy_level ALTER COLUMN id SET DEFAULT nextval('ap.approval_policy_level_id_seq'::regclass);


--
-- Name: approver_directory id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approver_directory ALTER COLUMN id SET DEFAULT nextval('ap.approver_directory_id_seq'::regclass);


--
-- Name: audit_log audit_log_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.audit_log ALTER COLUMN audit_log_id SET DEFAULT nextval('ap.audit_log_audit_log_id_seq'::regclass);


--
-- Name: cdc_failure_log id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.cdc_failure_log ALTER COLUMN id SET DEFAULT nextval('ap.cdc_failure_log_id_seq'::regclass);


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
-- Name: department_approver id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.department_approver ALTER COLUMN id SET DEFAULT nextval('ap.department_approver_id_seq'::regclass);


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

ALTER TABLE ONLY ap.invoice_approval ALTER COLUMN invoice_approval_id SET DEFAULT nextval('ap.invoice_approval_invoice_approval_id_seq1'::regclass);


--
-- Name: invoice_approval_legacy invoice_approval_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_legacy ALTER COLUMN invoice_approval_id SET DEFAULT nextval('ap.invoice_approval_invoice_approval_id_seq'::regclass);


--
-- Name: invoice_approval_step id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_step ALTER COLUMN id SET DEFAULT nextval('ap.invoice_approval_step_id_seq'::regclass);


--
-- Name: invoice_approval_step_approver id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_step_approver ALTER COLUMN id SET DEFAULT nextval('ap.invoice_approval_step_approver_id_seq'::regclass);


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
-- Name: nda_template id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.nda_template ALTER COLUMN id SET DEFAULT nextval('ap.nda_template_id_seq'::regclass);


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
-- Name: rfq id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.rfq ALTER COLUMN id SET DEFAULT nextval('ap.rfq_id_seq'::regclass);


--
-- Name: rfq_vendor id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.rfq_vendor ALTER COLUMN id SET DEFAULT nextval('ap.rfq_vendor_id_seq'::regclass);


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
-- Name: ums_role_cache role_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.ums_role_cache ALTER COLUMN role_id SET DEFAULT nextval('ap.ums_role_cache_role_id_seq'::regclass);


--
-- Name: ums_user_cache user_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.ums_user_cache ALTER COLUMN user_id SET DEFAULT nextval('ap.ums_user_cache_user_id_seq'::regclass);


--
-- Name: unit_of_measure id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.unit_of_measure ALTER COLUMN id SET DEFAULT nextval('ap.unit_of_measure_id_seq'::regclass);


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
-- Name: vendor_category_mapping vendor_category_mapping_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping ALTER COLUMN vendor_category_mapping_id SET DEFAULT nextval('ap.vendor_category_mapping_vendor_category_mapping_id_seq'::regclass);


--
-- Name: vendor_nda nda_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_nda ALTER COLUMN nda_id SET DEFAULT nextval('ap.vendor_nda_nda_id_seq'::regclass);


--
-- Name: vendor_onboarding_request id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_onboarding_request ALTER COLUMN id SET DEFAULT nextval('ap.vendor_onboarding_request_id_seq'::regclass);


--
-- Name: vendor_screening_rule id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_screening_rule ALTER COLUMN id SET DEFAULT nextval('ap.vendor_screening_rule_id_seq'::regclass);


--
-- Name: vendor_tax vendor_tax_id; Type: DEFAULT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_tax ALTER COLUMN vendor_tax_id SET DEFAULT nextval('ap.vendor_tax_vendor_tax_id_seq'::regclass);


--
-- Data for Name: approval_policy; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.approval_policy (id, name, department_id, purchase_category_id, is_active, created_at, updated_at, description, min_amount, max_amount, is_default) FROM stdin;
1	Test Policy	6	7	t	2026-09-16 14:18:39.572167+00	2026-09-16 14:18:39.572167+00	\N	0.00	100000.00	f
2	Default Policy	\N	\N	t	2026-09-16 15:33:50.47189+00	2026-09-18 12:17:06.76149+00	Catch-all fallback: applies only when no department+category+amount-scoped policy matches an invoice. Any active Super_Admin can approve.	\N	\N	t
\.


--
-- Data for Name: approval_policy_level; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.approval_policy_level (id, approval_policy_id, level_number, approver_type, approval_rule, is_active, created_at, updated_at, role_code, user_uuid) FROM stdin;
1	1	1	ROLE	ANY_ONE	t	2026-09-16 14:18:39.572167+00	2026-09-16 14:18:39.572167+00	Admin	\N
36	2	1	ROLE	ANY_ONE	t	2026-09-18 12:17:07.283427+00	2026-09-18 12:17:07.283427+00	Super_Admin	\N
\.


--
-- Data for Name: approver_directory; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.approver_directory (id, user_uuid, employee_uuid, department_uuid, is_user_active, created_at, updated_at, department_name) FROM stdin;
4	019e8c6f-9735-2eba-21f1-56f5d79c3256	019e8c6f-9735-2eba-21f1-56f5d79c3256	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:29:54.447647+00	2026-09-15 07:29:54.447647+00	Engineering
5	019e8c6f-9746-823d-0fd1-572e7ff403c8	019e8c6f-9746-823d-0fd1-572e7ff403c8	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:29:55.068141+00	2026-09-15 07:29:55.068141+00	Engineering
6	019e8c6f-9754-6bc2-8378-21c15fe06b71	019e8c6f-9754-6bc2-8378-21c15fe06b71	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:29:55.66778+00	2026-09-15 07:29:55.66778+00	Engineering
7	019e8c6f-97d0-6379-9078-0ba22e4ec921	019e8c6f-97d0-6379-9078-0ba22e4ec921	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:29:56.33133+00	2026-09-15 07:29:56.33133+00	Engineering
8	019e8c6f-9763-00c7-b39c-59c56712443c	019e8c6f-9763-00c7-b39c-59c56712443c	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:29:56.911022+00	2026-09-15 07:29:56.911022+00	Engineering
9	019e68eb-06b3-ae1c-03d8-27e8949646eb	019e68eb-06b3-ae1c-03d8-27e8949646eb	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:29:57.509092+00	2026-09-15 10:53:56.008301+00	Engineering
10	019e8c6f-9772-c412-1177-4759698bb1d6	019e8c6f-9772-c412-1177-4759698bb1d6	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:29:58.03217+00	2026-09-15 10:50:16.580879+00	Engineering
11	019e8c6f-97dc-c1a8-8790-1a2e9d1184a9	019e8c6f-97dc-c1a8-8790-1a2e9d1184a9	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:29:58.631231+00	2026-09-15 07:29:58.631231+00	Engineering
12	019e8c6f-9781-e1a7-f161-74e0cfbca3cf	019e8c6f-9781-e1a7-f161-74e0cfbca3cf	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:29:59.155472+00	2026-09-15 07:37:50.992284+00	Engineering
13	019e8c6f-978f-f260-6d86-d768ec44ba6d	019e8c6f-978f-f260-6d86-d768ec44ba6d	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:29:59.74432+00	2026-09-15 07:29:59.74432+00	Engineering
14	019e8c42-2660-4fd6-56c8-14bc05878344	019e8c42-2660-4fd6-56c8-14bc05878344	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:00.50349+00	2026-09-15 07:30:15.397955+00	Engineering
15	019e8c6f-979e-7e3e-8fa3-74a2d4a9edb6	019e8c6f-979e-7e3e-8fa3-74a2d4a9edb6	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:01.169879+00	2026-09-15 07:30:01.169879+00	Engineering
16	019e8c6f-97aa-842e-cde0-72514e55edda	019e8c6f-97aa-842e-cde0-72514e55edda	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:01.768433+00	2026-09-15 07:30:01.768433+00	Engineering
17	019e8c6f-97b7-9061-d9d1-4704d264f454	019e8c6f-97b7-9061-d9d1-4704d264f454	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:02.403388+00	2026-09-15 10:50:18.377521+00	Engineering
18	019e8c6f-97c4-e62e-52b0-11b9e4816c88	019e8c6f-97c4-e62e-52b0-11b9e4816c88	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:03.142946+00	2026-09-15 07:30:03.142946+00	Engineering
19	019e8c6f-97e9-b9ea-8af9-06af6c630bea	019e8c6f-97e9-b9ea-8af9-06af6c630bea	a36ca9b4-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:03.802233+00	2026-09-15 07:30:03.802233+00	Human Resource
20	019e8c25-0e73-7147-6bda-1279601ab9b4	019e8c25-0e73-7147-6bda-1279601ab9b4	a36cab48-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:04.399121+00	2026-09-15 07:30:04.399121+00	Management
21	019e8c6f-9812-9a50-5d66-fa4dca42de44	019e8c6f-9812-9a50-5d66-fa4dca42de44	a36ca9b4-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:04.9819+00	2026-09-15 07:30:04.9819+00	Human Resource
22	019e6973-3a4d-65c2-0b0a-34f73c5f18ee	019e6973-3a4d-65c2-0b0a-34f73c5f18ee	a36cab48-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:06.53271+00	2026-09-15 07:30:06.53271+00	Management
23	019e8c6f-97f6-9cd6-2ecb-9bb7916d5ec4	019e8c6f-97f6-9cd6-2ecb-9bb7916d5ec4	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:07.448121+00	2026-09-15 07:30:07.448121+00	Engineering
24	019e8c6f-9805-1c42-431e-15c89a2f1ad8	019e8c6f-9805-1c42-431e-15c89a2f1ad8	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:08.094007+00	2026-09-15 07:30:08.094007+00	Engineering
25	a858c3ff-9b6c-412f-8c64-b6803f817d9a	a858c3ff-9b6c-412f-8c64-b6803f817d9a	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:08.662046+00	2026-09-15 07:30:08.662046+00	Engineering
26	3e89bf42-0dda-4fc1-b67e-8590c0f444ad	3e89bf42-0dda-4fc1-b67e-8590c0f444ad	a36ca348-5992-11f1-bdde-027b59fbe807	t	2026-09-15 07:30:09.531989+00	2026-09-15 07:30:09.531989+00	Engineering
34	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	\N	t	2026-09-15 10:48:05.103801+00	2026-09-15 10:50:19.515812+00	\N
35	019e91fc-c2fd-0420-9cb1-29f5f71809bf	019e91fc-c2fd-0420-9cb1-29f5f71809bf	\N	t	2026-09-15 10:48:05.517437+00	2026-09-15 10:48:05.517437+00	\N
\.


--
-- Data for Name: approver_directory_role; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.approver_directory_role (id, user_uuid, role_id, role_code, is_active, created_at, updated_at) FROM stdin;
027c9fbb-2126-4dab-8820-ca2c5ac7ec74	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	7	Hr_Manager	t	2026-09-15 07:30:18.769788+00	2026-09-15 07:30:18.769788+00
078c1b9a-1490-4528-834a-f5addc2a53c7	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	2	Admin	t	2026-09-15 07:30:17.082845+00	2026-09-15 07:30:17.082845+00
0843e69c-b73f-41b5-ab80-63166b920113	019e91fc-c2fd-0420-9cb1-29f5f71809bf	38	System	t	2026-09-15 07:30:24.449197+00	2026-09-15 07:30:24.449197+00
09fdd1cc-ca2e-4281-b23f-96441d6f9f0c	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	33	Delivery_Manager	t	2026-09-15 07:30:21.690941+00	2026-09-15 07:30:21.690941+00
0c95169e-c558-451f-a6f6-c60f3937ae70	019e8c6f-97b7-9061-d9d1-4704d264f454	2	Admin	t	2026-09-15 07:30:50.593056+00	2026-09-15 07:30:50.593056+00
0f4cecbd-97db-42bc-be4c-f62f8e9cd801	019e8c6f-9735-2eba-21f1-56f5d79c3256	4	General	t	2026-09-15 07:30:25.664903+00	2026-09-15 07:30:25.664903+00
0ffbf716-767e-47f6-8fad-2e76d94e48a4	019e68eb-06b3-ae1c-03d8-27e8949646eb	2	Admin	t	2026-09-15 07:30:35.660028+00	2026-09-15 07:30:35.660028+00
11c4a5b3-ee0d-45c5-9edb-8b28d8b2482f	019e8c6f-97b7-9061-d9d1-4704d264f454	43	Finance_Executive	t	2026-09-15 07:30:52.551376+00	2026-09-15 07:30:52.551376+00
15044eb4-6115-4067-a991-f8442c87d123	01a0668d-084c-2662-6532-efd5dac60ff9	4	General	t	2026-09-15 07:41:31.99006+00	2026-09-15 07:41:31.99006+00
17dabf73-833a-4427-b25b-3a4e13c97df7	019e8c6f-97b7-9061-d9d1-4704d264f454	4	General	t	2026-09-15 07:30:51.634142+00	2026-09-15 07:30:51.634142+00
1854a583-1602-4325-8e26-b91612876749	019e8c6f-97c4-e62e-52b0-11b9e4816c88	4	General	t	2026-09-15 07:30:53.556208+00	2026-09-15 07:30:53.556208+00
1999fc62-8358-450a-b3fc-bf72d875fc5f	019e8c6f-9805-1c42-431e-15c89a2f1ad8	4	General	t	2026-09-15 07:41:16.008871+00	2026-09-15 07:41:16.008871+00
1a4c9a3c-e7d9-4afa-afb9-c02bc400c2cc	019e8c6f-978f-f260-6d86-d768ec44ba6d	2	Admin	t	2026-09-15 07:30:44.349951+00	2026-09-15 07:30:44.349951+00
1cd49dba-d7d7-493f-b4a4-4b749a4b90e9	019e8c6f-97d0-6379-9078-0ba22e4ec921	33	Delivery_Manager	t	2026-09-15 07:30:30.895541+00	2026-09-15 07:30:30.895541+00
1f5ad410-9333-4e41-a0bd-1e61024e5eaf	019e8c6f-97e9-b9ea-8af9-06af6c630bea	40	HIRING_MANAGER	t	2026-09-15 07:30:55.742307+00	2026-09-15 07:30:55.742307+00
218ccd86-3fb0-45d0-8574-e979e2254fb0	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	1	Super_Admin	t	2026-09-15 07:30:16.62378+00	2026-09-15 07:30:16.62378+00
21ae42c0-d79e-402b-b056-636e4448a26c	019e68eb-06b3-ae1c-03d8-27e8949646eb	43	Finance_Executive	t	2026-09-15 07:30:37.892368+00	2026-09-15 07:30:37.892368+00
2322ff5c-ffed-4df0-a0e0-25b0b81bdd5d	019e8c6f-979e-7e3e-8fa3-74a2d4a9edb6	3	HR	t	2026-09-15 07:30:47.364943+00	2026-09-15 07:30:47.364943+00
2807a2fc-8672-4113-9c22-5f39ba7a0c06	019fd71e-2bd0-af39-7b38-0b2a511b201e	48	PR_Approver	t	2026-09-15 10:54:16.158173+00	2026-09-15 10:54:16.158173+00
28c0f51d-492c-4bcc-9198-ec0784694a1d	019e8c6f-9772-c412-1177-4759698bb1d6	30	Project_Manager	t	2026-09-15 07:30:41.67711+00	2026-09-15 07:30:41.67711+00
3016085a-87ee-4e63-b4e7-97ebca2c4f7a	019e6973-3a4d-65c2-0b0a-34f73c5f18ee	31	Reporting_Manager	t	2026-09-15 07:41:11.675622+00	2026-09-15 07:41:11.675622+00
354110e4-dafc-43ee-ad0a-e7c4db9adbe2	019e8c6f-978f-f260-6d86-d768ec44ba6d	4	General	t	2026-09-15 07:30:44.810164+00	2026-09-15 07:30:44.810164+00
369e3844-4dd8-41a3-a7c0-bd5f04c1d33b	019e8c6f-97d0-6379-9078-0ba22e4ec921	45	AP_EXECUTIVE	t	2026-09-15 07:30:32.223457+00	2026-09-15 07:30:32.223457+00
3745e877-4da9-4959-b3e6-9125110e1171	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	4	General	t	2026-09-15 07:30:18.330216+00	2026-09-15 07:30:18.330216+00
37800a23-a9bb-4f1b-b38c-fe39be316b4a	019e8c6f-979e-7e3e-8fa3-74a2d4a9edb6	30	Project_Manager	t	2026-09-15 07:30:48.323604+00	2026-09-15 07:30:48.323604+00
39144097-0900-493c-b671-76fb72e1f0ac	019e8c6f-97aa-842e-cde0-72514e55edda	30	Project_Manager	t	2026-09-15 07:30:49.283384+00	2026-09-15 07:30:49.283384+00
3f0b6785-8917-47ed-aa46-d961368c202e	019e8c6f-9735-2eba-21f1-56f5d79c3256	1	Super_Admin	t	2026-09-15 07:30:24.869196+00	2026-09-15 07:30:24.869196+00
41bd003b-519a-4947-98bc-3cff6fd81257	019e6973-3a4d-65c2-0b0a-34f73c5f18ee	4	General	t	2026-09-15 07:41:09.573113+00	2026-09-15 07:41:09.573113+00
47b74002-da0e-4df6-a860-806195a2a660	019fd71e-2bd0-af39-7b38-0b2a511b201e	42	Vendor_Intake	t	2026-09-15 11:00:25.41334+00	2026-09-15 11:00:25.41334+00
4d0fc9fb-5cac-4228-8542-c586936238b3	019e8c6f-97d0-6379-9078-0ba22e4ec921	4	General	t	2026-09-15 07:30:30.162813+00	2026-09-15 07:30:30.162813+00
4e0029fc-c104-4ab3-a7e2-6adacfb7abf5	01a06b23-3a83-55f9-1781-87f59ad9f9be	4	General	t	2026-09-15 07:41:34.19242+00	2026-09-15 07:41:34.19242+00
50a08699-fb25-4a2f-96b8-77acdb8fe640	019e68eb-06b3-ae1c-03d8-27e8949646eb	4	General	t	2026-09-15 07:30:36.291066+00	2026-09-15 07:30:36.291066+00
50f64cb4-0e8a-47f7-abb4-e51ff6849ce6	019e8c6f-97dc-c1a8-8790-1a2e9d1184a9	4	General	t	2026-09-15 07:30:42.424865+00	2026-09-15 07:30:42.424865+00
50fbafb0-0178-4ee9-afff-8ba67b74a955	019e68eb-06b3-ae1c-03d8-27e8949646eb	1	Super_Admin	t	2026-09-15 07:30:35.22286+00	2026-09-15 07:30:35.22286+00
51aa3120-0bd1-4e7b-9789-35290b5b3a0b	019e8c6f-9763-00c7-b39c-59c56712443c	4	General	t	2026-09-15 07:30:34.216641+00	2026-09-15 07:30:34.216641+00
53449250-12cc-4bcb-9b3c-7c165a2adc21	019e8c6f-978f-f260-6d86-d768ec44ba6d	30	Project_Manager	t	2026-09-15 07:30:45.499707+00	2026-09-15 07:30:45.499707+00
56ffd620-3ea5-4791-9821-f53765e3a914	3e89bf42-0dda-4fc1-b67e-8590c0f444ad	4	General	t	2026-09-15 07:41:20.978061+00	2026-09-15 07:41:20.978061+00
574a6138-3b20-403d-ae14-1d17bc9bd3d5	019e6973-3a4d-65c2-0b0a-34f73c5f18ee	1	Super_Admin	t	2026-09-15 07:41:09.097646+00	2026-09-15 07:41:09.097646+00
576569e1-3d41-42f4-aca0-4b6b83135053	019e6973-3a4d-65c2-0b0a-34f73c5f18ee	30	Project_Manager	t	2026-09-15 07:41:10.550691+00	2026-09-15 07:41:10.550691+00
58c1e2f7-d24c-46a0-b1ba-1bf6cf43fc24	019e8c6f-97e9-b9ea-8af9-06af6c630bea	39	HR_ADMIN	t	2026-09-15 07:30:55.221078+00	2026-09-15 07:30:55.221078+00
58da75f2-1a49-437f-958b-285d361607d1	019e68eb-06b3-ae1c-03d8-27e8949646eb	49	Procurement_Officer	t	2026-09-15 07:30:38.544589+00	2026-09-15 07:30:38.544589+00
58f7a744-419a-4a62-82a1-6b1d62dd7558	019e8c6f-97b7-9061-d9d1-4704d264f454	1	Super_Admin	t	2026-09-15 07:30:49.96381+00	2026-09-15 07:30:49.96381+00
5e4366a3-6071-4ed8-ae8e-c047d4147f7e	019e8c6f-9812-9a50-5d66-fa4dca42de44	41	RECRUITER	t	2026-09-15 07:41:07.358941+00	2026-09-15 07:41:07.358941+00
60b228e7-67f5-43f2-9e3c-5a42482f5df9	019e8c6f-9812-9a50-5d66-fa4dca42de44	42	Vendor_Intake	t	2026-09-15 07:41:07.960432+00	2026-09-15 07:41:07.960432+00
67d195cd-27dd-4f26-8906-c3cfc2b40372	01a06627-8abd-15cf-8a40-11027aacd5f9	4	General	t	2026-09-15 07:41:30.275884+00	2026-09-15 07:41:30.275884+00
72fca749-8f6d-4493-bff2-92f66fb6db7a	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	37	Tester	t	2026-09-15 07:30:23.116862+00	2026-09-15 07:30:23.116862+00
79172b59-fbf8-4e6d-866f-a083c06c81df	019e68eb-06b3-ae1c-03d8-27e8949646eb	30	Project_Manager	t	2026-09-15 07:30:36.828846+00	2026-09-15 07:30:36.828846+00
7d84cbca-b673-4ddf-8560-40f9b7d439d0	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	30	Project_Manager	t	2026-09-15 07:30:19.265729+00	2026-09-15 07:30:19.265729+00
7df74753-3497-4c45-bc67-205d6ea642e7	019e8c6f-9754-6bc2-8378-21c15fe06b71	45	AP_EXECUTIVE	t	2026-09-15 07:30:29.60807+00	2026-09-15 07:30:29.60807+00
7ff8ed1c-45dc-40ef-9fda-c6e232c89845	019e8c6f-9754-6bc2-8378-21c15fe06b71	39	HR_ADMIN	t	2026-09-15 07:30:29.144226+00	2026-09-15 07:30:29.144226+00
82fe2d1a-57f5-4df1-96b6-9b707e07b79d	019e8c6f-9781-e1a7-f161-74e0cfbca3cf	33	Delivery_Manager	t	2026-09-15 07:30:43.82015+00	2026-09-15 07:30:43.82015+00
8317604e-ee60-468d-a4b5-91e8663c2358	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	3	HR	t	2026-09-15 07:30:17.830918+00	2026-09-15 07:30:17.830918+00
878be4a3-0bc6-4e4d-85a3-6ec3ae92f711	019e8c6f-9812-9a50-5d66-fa4dca42de44	49	Procurement_Officer	t	2026-09-15 07:41:08.529939+00	2026-09-15 07:41:08.529939+00
8dc9c1d8-db15-4845-b8b5-9c7b21b7755a	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	32	Resource_Manager	t	2026-09-15 07:30:20.453541+00	2026-09-15 07:30:20.453541+00
8ef8acdb-6e46-4b12-ad89-5c49769fd47c	019e8c25-0e73-7147-6bda-1279601ab9b4	31	Reporting_Manager	t	2026-09-15 07:30:57.440866+00	2026-09-15 07:30:57.440866+00
9755f8f2-6d22-46db-b2ac-e2886087e83e	a858c3ff-9b6c-412f-8c64-b6803f817d9a	4	General	t	2026-09-15 07:41:19.10802+00	2026-09-15 07:41:19.10802+00
97830d5e-cf35-498f-9641-06114e9ef284	019fd71e-2bd0-af39-7b38-0b2a511b201e	4	General	t	2026-09-08 14:05:25.121024+00	2026-09-15 07:41:24.807365+00
a5421b11-9b86-4f25-9285-75dd8483de96	ae79c79e-40f7-4126-935d-2a37f6195f9c	4	General	t	2026-09-15 07:41:22.3879+00	2026-09-15 07:41:22.3879+00
a9175f02-e794-4d30-85e2-70a90011ae6c	019e8c6f-9754-6bc2-8378-21c15fe06b71	4	General	t	2026-09-15 07:30:27.747576+00	2026-09-15 07:30:27.747576+00
ac74d252-f61a-42a5-b89f-b3f8f5a89ea1	019e8c6f-97aa-842e-cde0-72514e55edda	4	General	t	2026-09-15 07:30:48.82426+00	2026-09-15 07:30:48.82426+00
b32ec470-6704-460e-91c5-c6658751a659	019e8c6f-9805-1c42-431e-15c89a2f1ad8	45	AP_EXECUTIVE	t	2026-09-15 07:41:17.737822+00	2026-09-15 07:41:17.737822+00
b49dc825-20f8-41fa-ad36-5074d2cd22a9	019e8c6f-979e-7e3e-8fa3-74a2d4a9edb6	4	General	t	2026-09-15 07:30:47.865112+00	2026-09-15 07:30:47.865112+00
b61e944f-dfb3-4f8c-9daa-bea83d252582	019e8c6f-9772-c412-1177-4759698bb1d6	4	General	t	2026-09-15 07:30:39.172514+00	2026-09-15 07:30:39.172514+00
b65b3cca-accb-45ca-860c-42b8e1455537	019e8c6f-978f-f260-6d86-d768ec44ba6d	31	Reporting_Manager	t	2026-09-15 07:30:45.943978+00	2026-09-15 07:30:45.943978+00
b943623e-a910-43ef-b49c-4dcf12b4e5df	019e8c6f-9772-c412-1177-4759698bb1d6	7	Hr_Manager	t	2026-09-15 07:30:40.24427+00	2026-09-15 07:30:40.24427+00
b9f0cb44-1201-4f35-b5e1-bcaa07eb0f2b	019e8c6f-9812-9a50-5d66-fa4dca42de44	4	General	t	2026-09-15 07:30:57.949939+00	2026-09-15 07:30:57.949939+00
ba5e7143-5a5d-46c6-b81d-0d7d81feddc8	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	31	Reporting_Manager	t	2026-09-15 07:30:19.63674+00	2026-09-15 07:30:19.63674+00
bb1c0bf7-dd97-4715-8437-4efca6166bbf	019e8c6f-97e9-b9ea-8af9-06af6c630bea	41	RECRUITER	t	2026-09-15 07:30:56.20371+00	2026-09-15 07:30:56.20371+00
bd1f2695-e241-4dd8-85c7-0abb0f7477ff	019e8c6f-9763-00c7-b39c-59c56712443c	31	Reporting_Manager	t	2026-09-15 07:30:34.755473+00	2026-09-15 07:30:34.755473+00
bee65dc3-56aa-4441-9a41-1e0af6fbcdad	019e91fc-c2fd-0420-9cb1-29f5f71809bf	4	General	t	2026-09-15 07:30:23.970704+00	2026-09-15 07:30:23.970704+00
c0b25845-029f-4a2f-ab1e-0be28b6dc741	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	39	HR_ADMIN	t	2026-09-15 07:30:23.549142+00	2026-09-15 07:30:23.549142+00
c1f887c7-a5ff-4eec-a651-aa469e0b2124	019e8c6f-97f6-9cd6-2ecb-9bb7916d5ec4	46	Finance_Manager	t	2026-09-15 07:41:14.427391+00	2026-09-15 07:41:14.427391+00
c4e6daf2-7da2-4c24-aad4-53bf9467feba	019e8c25-0e73-7147-6bda-1279601ab9b4	4	General	t	2026-09-15 07:30:56.842701+00	2026-09-15 07:30:56.842701+00
c5ae1bc3-7161-4234-96fb-eb972d017133	019e68eb-06b3-ae1c-03d8-27e8949646eb	31	Reporting_Manager	t	2026-09-15 07:30:37.372568+00	2026-09-15 07:30:37.372568+00
c7d59a06-91e7-4b16-8910-508cac147366	019e8c6f-9754-6bc2-8378-21c15fe06b71	3	HR	t	2026-09-15 07:30:26.583306+00	2026-09-15 07:30:26.583306+00
caeeb370-e8b5-4a15-add4-64fb19e4945a	019e8c6f-9746-823d-0fd1-572e7ff403c8	4	General	t	2026-09-15 07:30:26.155593+00	2026-09-15 07:30:26.155593+00
cb9b12a2-490a-4585-976b-884eb601f25c	019e8c42-2660-4fd6-56c8-14bc05878344	30	Project_Manager	t	2026-09-15 07:30:46.776497+00	2026-09-15 07:30:46.776497+00
cf09ff63-5e62-4225-8634-3a604e719f7e	01a06628-e2bb-6570-330f-e37ab1f83be8	4	General	t	2026-09-15 07:41:31.040613+00	2026-09-15 07:41:31.040613+00
d8c3fa82-2acc-46af-9258-ba7c9939d795	019e8c6f-9735-2eba-21f1-56f5d79c3256	2	Admin	t	2026-09-15 07:30:25.261528+00	2026-09-15 07:30:25.261528+00
df3c081c-fa18-4741-b197-1cae804af39c	019e8c6f-97d0-6379-9078-0ba22e4ec921	47	PR_Creator	t	2026-09-15 07:30:33.56352+00	2026-09-15 07:30:33.56352+00
e2f9690a-44ce-42e1-9ae5-603ff6c2322a	01a066a2-3428-cb47-9c83-2c8834bcbc35	4	General	t	2026-09-15 07:41:33.100482+00	2026-09-15 07:41:33.100482+00
e44a6e50-e83d-47dd-a517-4b8b5d760e06	019e8c6f-97e9-b9ea-8af9-06af6c630bea	3	HR	t	2026-09-15 07:30:54.145555+00	2026-09-15 07:30:54.145555+00
f2fae64b-94f5-47f0-8b88-a53fc844dfc7	019e8c6f-97e9-b9ea-8af9-06af6c630bea	4	General	t	2026-09-15 07:30:54.723827+00	2026-09-15 07:30:54.723827+00
f6c288b0-33c7-49f3-a9d2-87e09989dc1d	01a06b2a-1760-d68a-b150-64da98bd16d5	4	General	t	2026-09-15 07:41:35.345982+00	2026-09-15 07:41:35.345982+00
f9dd771d-73bb-420b-879d-d45d7835e49c	019e8c6f-9781-e1a7-f161-74e0cfbca3cf	4	General	t	2026-09-15 07:30:42.968359+00	2026-09-15 07:30:42.968359+00
fba77731-bee2-4931-bb27-515a258d84b9	019e8c6f-9781-e1a7-f161-74e0cfbca3cf	32	Resource_Manager	t	2026-09-15 07:30:43.42755+00	2026-09-15 07:30:43.42755+00
fbce6c3d-657b-445f-9730-2b9852616a3c	019e8c42-2660-4fd6-56c8-14bc05878344	4	General	t	2026-09-15 07:30:46.350861+00	2026-09-15 07:30:46.350861+00
fd6dfa10-a79b-4990-9d59-1319ee880cff	019e8c6f-97f6-9cd6-2ecb-9bb7916d5ec4	4	General	t	2026-09-15 07:41:12.812778+00	2026-09-15 07:41:12.812778+00
\.


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
97	purchase_requisition	5	APPROVED	1	2026-09-03 09:14:14.983386	\N	null
98	purchase_requisition	6	APPROVED	1	2026-09-03 12:00:53.283536	\N	{"comment": "Approved for procurement"}
99	rfq	1	EMAIL_FAILED	1	2026-09-03 12:13:32.140182	\N	{"email": "support.aws@example.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 15}
100	rfq	1	EMAIL_FAILED	1	2026-09-03 12:13:32.140182	\N	{"email": "admin.keka@keka.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
101	rfq	1	EMAIL_FAILED	1	2026-09-03 12:22:07.87512	\N	{"email": "21311a04e1@sreenidhi.edu.in", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 15}
102	rfq	1	EMAIL_FAILED	1	2026-09-03 12:22:07.87512	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
103	rfq	1	EMAIL_FAILED	1	2026-09-03 12:22:40.494822	\N	{"email": "21311a04e1@sreenidhi.edu.in", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 15}
104	rfq	1	EMAIL_FAILED	1	2026-09-03 12:22:40.494822	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
105	rfq	1	EMAIL_FAILED	1	2026-09-03 12:25:16.660368	\N	{"email": "viratvenky207@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 15}
106	rfq	1	EMAIL_FAILED	1	2026-09-03 12:25:16.660368	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
107	rfq	1	EMAIL_FAILED	1	2026-09-03 12:25:22.456745	\N	{"email": "viratvenky207@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 15}
108	rfq	1	EMAIL_FAILED	1	2026-09-03 12:25:22.456745	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
109	rfq	1	EMAIL_FAILED	1	2026-09-03 12:34:41.403823	\N	{"email": "viratvenky207@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 15}
110	rfq	1	EMAIL_FAILED	1	2026-09-03 12:34:41.403823	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
111	rfq	1	EMAIL_FAILED	1	2026-09-03 12:35:57.608828	\N	{"email": "viratvenky207@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 15}
112	rfq	1	EMAIL_FAILED	1	2026-09-03 12:35:57.608828	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
113	rfq	1	EMAIL_FAILED	1	2026-09-03 12:36:32.204688	\N	{"email": "viratvenky207@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 15}
114	rfq	1	EMAIL_FAILED	1	2026-09-03 12:36:32.204688	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
115	rfq	1	EMAIL_FAILED	diagnostic-test	2026-09-03 12:47:27.820512	\N	{"email": "viratvenky207@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 15}
116	rfq	1	EMAIL_FAILED	diagnostic-test	2026-09-03 12:47:27.820512	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
117	rfq	1	EMAIL_FAILED	1	2026-09-03 13:00:25.790059	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-1431990a65bsm5916841c88.5 - gsmtp')", "vendor_id": 15}
118	rfq	1	EMAIL_FAILED	1	2026-09-03 13:00:25.790059	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325592da63sm6022328eec.13 - gsmtp')", "vendor_id": 16}
119	rfq	1	EMAIL_FAILED	1	2026-09-03 13:00:38.794483	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325680c369sm6520566eec.28 - gsmtp')", "vendor_id": 15}
120	rfq	1	EMAIL_FAILED	1	2026-09-03 13:00:38.794483	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-1431990a39bsm5418601c88.3 - gsmtp')", "vendor_id": 16}
121	rfq	1	EMAIL_FAILED	1	2026-09-03 13:03:32.950027	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-33255f2981dsm6749493eec.19 - gsmtp')", "vendor_id": 15}
122	rfq	1	EMAIL_FAILED	1	2026-09-03 13:03:32.950027	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325534cd65sm7555904eec.6 - gsmtp')", "vendor_id": 16}
123	rfq	1	EMAIL_FAILED	1	2026-09-03 13:08:27.732935	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325671421bsm6135562eec.27 - gsmtp')", "vendor_id": 15}
124	rfq	1	EMAIL_FAILED	1	2026-09-03 13:08:27.732935	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-1431f86504fsm5375930c88.4 - gsmtp')", "vendor_id": 16}
125	rfq	1	EMAIL_FAILED	diagnostic-test-2	2026-09-03 13:12:46.182118	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-14319785bd8sm10885702c88.0 - gsmtp')", "vendor_id": 15}
126	rfq	1	EMAIL_FAILED	diagnostic-test-2	2026-09-03 13:12:46.182118	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-33253672941sm6628818eec.3 - gsmtp')", "vendor_id": 16}
127	rfq	1	EMAIL_FAILED	1	2026-09-03 13:29:54.015741	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325641b4dcsm6341159eec.26 - gsmtp')", "vendor_id": 15}
128	rfq	1	EMAIL_FAILED	1	2026-09-03 13:29:54.015741	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-1431997dd07sm6358089c88.14 - gsmtp')", "vendor_id": 16}
129	rfq	1	EMAIL_FAILED	1	2026-09-03 13:30:43.700143	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-1431991f777sm5960494c88.6 - gsmtp')", "vendor_id": 15}
130	rfq	1	EMAIL_FAILED	1	2026-09-03 13:30:43.700143	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325592ebb3sm7030431eec.14 - gsmtp')", "vendor_id": 16}
131	rfq	1	EMAIL_FAILED	diagnostic-test-3	2026-09-03 13:35:18.719726	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3332d788fa1sm2499370eec.7 - gsmtp')", "vendor_id": 15}
132	rfq	1	EMAIL_FAILED	diagnostic-test-3	2026-09-03 13:35:18.719726	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325534c324sm7332723eec.5 - gsmtp')", "vendor_id": 16}
133	rfq	1	EMAIL_FAILED	1	2026-09-03 13:40:34.210497	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325534e100sm7699094eec.9 - gsmtp')", "vendor_id": 15}
134	rfq	1	EMAIL_FAILED	1	2026-09-03 13:40:34.210497	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325592d9c5sm7313669eec.11 - gsmtp')", "vendor_id": 16}
135	rfq	1	EMAIL_FAILED	1	2026-09-03 13:40:45.921891	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-14319983842sm6982131c88.15 - gsmtp')", "vendor_id": 15}
136	rfq	1	EMAIL_FAILED	1	2026-09-03 13:40:45.921891	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-33253672933sm12174684eec.4 - gsmtp')", "vendor_id": 16}
137	rfq	1	EMAIL_FAILED	1	2026-09-03 13:42:56.232635	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-14319922eb4sm6119765c88.7 - gsmtp')", "vendor_id": 15}
138	rfq	1	EMAIL_FAILED	1	2026-09-03 13:42:56.232635	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325631eed2sm7774101eec.22 - gsmtp')", "vendor_id": 16}
139	rfq	1	EMAIL_FAILED	diagnostic-test-4	2026-09-03 13:46:39.615737	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325592ebb3sm7143401eec.14 - gsmtp')", "vendor_id": 15}
140	rfq	1	EMAIL_FAILED	diagnostic-test-4	2026-09-03 13:46:39.615737	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325534e83csm7323092eec.10 - gsmtp')", "vendor_id": 16}
141	rfq	1	EMAIL_FAILED	1	2026-09-03 13:56:03.461814	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-1431993de23sm6354661c88.8 - gsmtp')", "vendor_id": 15}
142	rfq	1	EMAIL_FAILED	1	2026-09-03 13:56:03.461814	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-1431993de23sm6355024c88.8 - gsmtp')", "vendor_id": 16}
143	rfq	1	EMAIL_FAILED	1	2026-09-03 13:56:16.1396	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-1431995f4e9sm8467990c88.11 - gsmtp')", "vendor_id": 15}
144	rfq	1	EMAIL_FAILED	1	2026-09-03 13:56:16.1396	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325631eed2sm7868479eec.22 - gsmtp')", "vendor_id": 16}
145	rfq	1	EMAIL_FAILED	1	2026-09-03 13:58:11.156948	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-33256903a21sm6801053eec.30 - gsmtp')", "vendor_id": 15}
146	rfq	1	EMAIL_FAILED	1	2026-09-03 13:58:11.156948	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325592da63sm6374710eec.13 - gsmtp')", "vendor_id": 16}
147	rfq	1	EMAIL_FAILED	1	2026-09-03 13:58:23.767908	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325592e2afsm6240949eec.12 - gsmtp')", "vendor_id": 15}
148	rfq	1	EMAIL_FAILED	1	2026-09-03 13:58:23.767908	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-3325534c324sm7489194eec.5 - gsmtp')", "vendor_id": 16}
149	rfq	1	EMAIL_FAILED	1	2026-09-03 13:59:40.967346	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-143199692a6sm11016141c88.12 - gsmtp')", "vendor_id": 15}
150	rfq	1	EMAIL_FAILED	1	2026-09-03 13:59:40.967346	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-33255d39d21sm8016757eec.16 - gsmtp')", "vendor_id": 16}
151	rfq	1	EMAIL_FAILED	1	2026-09-03 14:01:39.195468	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-332501e5447sm9728365eec.0 - gsmtp')", "vendor_id": 15}
152	rfq	1	EMAIL_FAILED	1	2026-09-03 14:01:39.195468	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-1431997dd07sm6539781c88.14 - gsmtp')", "vendor_id": 16}
153	rfq	1	EMAIL_FAILED	1	2026-09-03 14:01:53.069805	\N	{"email": "viratvenky207@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials a92af1059eb24-1431997dd07sm6540716c88.14 - gsmtp')", "vendor_id": 15}
154	rfq	1	EMAIL_FAILED	1	2026-09-03 14:01:53.069805	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "(535, b'5.7.8 Username and Password not accepted. For more information, go to\\\\n5.7.8  https://support.google.com/mail/?p=BadCredentials 5a478bee46e88-33255d39d21sm8033487eec.16 - gsmtp')", "vendor_id": 16}
155	rfq	1	EMAIL_SENT	1	2026-09-03 14:06:41.981409	\N	{"email": "viratvenky207@gmail.com", "error": null, "vendor_id": 15}
156	rfq	1	EMAIL_SENT	1	2026-09-03 14:06:41.981409	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": null, "vendor_id": 16}
157	purchase_requisition	7	RETURNED	1	2026-09-04 08:04:51.060415	\N	{"comment": "provide me specification of this laptop"}
158	purchase_requisition	7	RESUBMITTED	1	2026-09-04 09:05:26.522342	\N	{"comment": "provide me specification of this laptop"}
159	purchase_requisition	7	RESUBMITTED	1	2026-09-04 09:10:12.973325	\N	{"comment": "provide me specification of this laptop"}
160	purchase_requisition	7	RETURNED	1	2026-09-04 09:10:38.944613	\N	{"comment": "provide me charging capacity"}
161	purchase_requisition	7	RESUBMITTED	1	2026-09-04 09:11:04.568633	\N	{"comment": "provide me charging capacity"}
162	purchase_requisition	7	APPROVED	1	2026-09-04 09:11:18.042157	\N	null
163	rfq	2	EMAIL_SENT	1	2026-09-04 09:14:36.55963	\N	{"email": "viratvenky207@gmail.com", "error": null, "vendor_id": 15}
164	rfq	2	EMAIL_SENT	1	2026-09-04 09:14:36.55963	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": null, "vendor_id": 16}
165	purchase_requisition	8	RETURNED	1	2026-09-04 09:38:21.10374	\N	{"comment": "i need speciation of the laptop"}
166	purchase_requisition	8	RESUBMITTED	1	2026-09-04 09:38:33.1326	\N	{"comment": "i need speciation of the laptop"}
167	purchase_requisition	8	APPROVED	1	2026-09-04 09:38:46.793234	\N	null
168	rfq	3	EMAIL_SENT	1	2026-09-04 09:40:00.465096	\N	{"email": "viratvenky207@gmail.com", "error": null, "vendor_id": 15}
169	rfq	3	EMAIL_SENT	1	2026-09-04 09:40:00.465096	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": null, "vendor_id": 16}
170	purchase_requisition	10	RETURNED	5100031	2026-09-07 11:15:36.165991	\N	{"comment": "i think we have already requested for those laptops"}
171	purchase_requisition	10	RESUBMITTED	5100007	2026-09-07 11:19:06.951225	\N	{"comment": "i think we have already requested for those laptops"}
172	purchase_requisition	10	RETURNED	5100031	2026-09-07 11:21:56.87978	\N	{"comment": "i think we already requested this items"}
173	purchase_requisition	10	RESUBMITTED	5100007	2026-09-07 11:23:15.141634	\N	{"comment": "i think we already requested this items"}
174	purchase_requisition	10	APPROVED	5100031	2026-09-07 11:24:21.209795	\N	null
175	rfq	4	EMAIL_FAILED	5100009	2026-09-07 11:28:55.493684	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
176	rfq	4	EMAIL_FAILED	5100009	2026-09-07 11:29:11.121012	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
177	rfq	4	EMAIL_FAILED	5100009	2026-09-07 11:32:09.253916	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
178	rfq	4	EMAIL_FAILED	5100009	2026-09-07 11:33:28.799481	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
179	rfq	4	EMAIL_FAILED	5100009	2026-09-07 11:36:55.658608	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
180	rfq	4	EMAIL_FAILED	5100009	2026-09-07 11:37:21.750531	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
181	rfq	4	EMAIL_FAILED	5100009	2026-09-07 11:38:19.9077	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 16}
182	purchase_requisition	11	RETURNED	5100031	2026-09-07 12:38:37.480569	\N	{"comment": "i need in detail specifications"}
183	purchase_requisition	12	RETURNED	5100031	2026-09-07 12:47:05.062143	\N	{"comment": "need some more specifications"}
184	purchase_requisition	12	RESUBMITTED	5100007	2026-09-07 13:47:30.023421	\N	{"comment": "need some more specifications"}
185	purchase_requisition	12	RETURNED	5100031	2026-09-07 13:48:18.608093	\N	{"comment": "need specifications"}
186	purchase_requisition	13	RETURNED	5100031	2026-09-08 06:26:13.081707	\N	{"comment": "need specifications"}
187	purchase_requisition	13	RESUBMITTED	5100007	2026-09-08 06:26:56.85931	\N	{"comment": "need specifications"}
188	purchase_requisition	13	RETURNED	5100031	2026-09-08 06:27:33.954349	\N	{"comment": "nothing"}
189	purchase_requisition	12	RESUBMITTED	5100007	2026-09-08 06:36:10.390758	\N	{"comment": "need specifications"}
190	purchase_requisition	12	APPROVED	5100031	2026-09-08 06:36:33.478181	\N	null
191	rfq	5	EMAIL_SENT	5100024	2026-09-08 06:47:03.533315	\N	{"email": "viratvenky207@gmail.com", "error": null, "vendor_id": 15}
192	rfq	5	EMAIL_SENT	5100024	2026-09-08 06:47:03.533315	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": null, "vendor_id": 16}
193	rfq	4	EMAIL_SENT	5100024	2026-09-08 06:54:29.095702	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": null, "vendor_id": 16}
194	purchase_requisition	13	PR_RESUBMITTED	5100007	2026-09-08 09:20:18.47602	\N	{"reason": "nothing"}
195	purchase_requisition	13	PR_APPROVED	5100031	2026-09-08 09:20:44.444017	\N	null
196	purchase_requisition	15	PR_REQUEST_RAISED	5100007	2026-09-08 09:29:36.645959	\N	null
222	purchase_requisition	15	SUBMITTED_FOR_APPROVAL	5100007	2026-09-08 12:01:36.399139	\N	null
223	purchase_requisition	15	PR_SENT_BACK_FOR_CLARIFICATION	5100031	2026-09-08 12:02:18.480309	\N	{"reason": "need some more clarification"}
224	purchase_requisition	15	PR_RESUBMITTED	5100007	2026-09-08 12:03:32.361742	\N	{"reason": "need some more clarification"}
225	purchase_requisition	15	PR_SENT_BACK_FOR_CLARIFICATION	5100031	2026-09-08 12:04:47.828842	\N	{"reason": "need some more information about this things"}
226	purchase_requisition	15	PR_RESUBMITTED	5100007	2026-09-08 12:05:18.689645	\N	{"reason": "need some more information about this things"}
227	purchase_requisition	15	PR_APPROVED	5100031	2026-09-08 12:06:03.667358	\N	null
228	purchase_requisition	13	VENDOR_INVITED	5100024	2026-09-08 12:18:31.498043	\N	{"rfq_id": 9, "vendor_ids": [15]}
229	purchase_requisition	13	VENDOR_INVITED	5100024	2026-09-08 12:18:59.483711	\N	{"rfq_id": 9, "vendor_ids": [16]}
230	purchase_requisition	10	VENDOR_INVITED	5100024	2026-09-08 12:20:30.384842	\N	{"rfq_id": 4, "vendor_ids": [15]}
231	purchase_requisition	10	QUOTATION_RECEIVED	5100024	2026-09-08 12:21:52.789936	\N	{"vendor_id": 15, "quotation_id": 11}
232	purchase_requisition	10	QUOTATION_RECEIVED	5100024	2026-09-08 12:24:35.752195	\N	{"vendor_id": 15, "quotation_id": 12}
233	purchase_requisition	20	PR_REQUEST_RAISED	5100007	2026-09-08 12:28:19.26133	\N	null
234	purchase_requisition	20	SUBMITTED_FOR_APPROVAL	5100007	2026-09-08 12:34:44.623266	\N	null
235	purchase_requisition	20	PR_SENT_BACK_FOR_CLARIFICATION	5100031	2026-09-08 12:35:20.004938	\N	{"reason": "need specifications"}
236	purchase_requisition	20	PR_RESUBMITTED	5100007	2026-09-08 12:37:33.292387	\N	{"reason": "need specifications"}
237	purchase_requisition	20	PR_SENT_BACK_FOR_CLARIFICATION	5100031	2026-09-08 12:38:17.713143	\N	{"reason": "need detail summary"}
238	purchase_requisition	20	PR_RESUBMITTED	5100007	2026-09-08 12:38:53.391121	\N	{"reason": "need detail summary"}
239	purchase_requisition	20	PR_APPROVED	5100031	2026-09-08 12:39:26.670626	\N	null
240	purchase_requisition	20	VENDOR_INVITED	5100024	2026-09-08 12:40:05.872402	\N	{"rfq_id": 10, "vendor_ids": [15, 16]}
241	purchase_requisition	20	QUOTATION_RECEIVED	5100024	2026-09-08 12:42:21.129599	\N	{"rfq_id": 10, "vendor_id": 15, "quotation_id": 13}
242	purchase_requisition	13	QUOTATION_RECEIVED	5100024	2026-09-08 12:49:24.706639	\N	{"rfq_id": 9, "vendor_id": 15, "quotation_id": 14}
243	purchase_requisition	13	QUOTATION_RECEIVED	5100024	2026-09-08 12:50:31.14443	\N	{"rfq_id": 9, "vendor_id": 16, "quotation_id": 15}
244	purchase_requisition	15	VENDOR_INVITED	5100024	2026-09-08 12:59:35.329981	\N	{"rfq_id": 8, "vendor_ids": [15, 16]}
245	purchase_requisition	21	PR_REQUEST_RAISED	5100007	2026-09-08 13:29:18.400785	\N	null
246	purchase_requisition	21	SUBMITTED_FOR_APPROVAL	5100007	2026-09-08 13:29:50.487047	\N	null
247	purchase_requisition	21	PR_APPROVED	5100031	2026-09-08 13:30:18.252883	\N	null
248	purchase_requisition	21	VENDOR_INVITED	5100024	2026-09-08 13:30:57.376516	\N	{"rfq_id": 11, "vendor_ids": [15, 16]}
249	purchase_requisition	5	VENDOR_INVITED	5100024	2026-09-09 06:50:16.762414	\N	{"rfq_id": 12, "vendor_ids": [15, 16]}
250	rfq	10	EMAIL_SENT	5100024	2026-09-09 07:07:06.171437	\N	{"email": "viratvenky207@gmail.com", "error": null, "vendor_id": 15}
251	rfq	10	EMAIL_SENT	5100024	2026-09-09 07:07:06.171437	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": null, "vendor_id": 16}
252	purchase_requisition	20	RFQ_SENT	5100024	2026-09-09 07:07:06.171437	\N	{"rfq_id": 10, "failed_count": 0, "vendor_count": 2}
253	purchase_requisition	22	PR_REQUEST_RAISED	5100007	2026-09-09 07:11:39.673308	\N	null
254	purchase_requisition	22	SUBMITTED_FOR_APPROVAL	5100007	2026-09-09 07:12:27.149134	\N	null
255	purchase_requisition	22	PR_SENT_BACK_FOR_CLARIFICATION	5100031	2026-09-09 07:13:14.699408	\N	{"reason": "indetail details"}
256	purchase_requisition	22	PR_UPDATED	5100007	2026-09-09 07:14:01.765383	\N	null
257	purchase_requisition	22	PR_RESUBMITTED	5100007	2026-09-09 07:14:29.672188	\N	{"reason": "indetail details"}
258	purchase_requisition	22	PR_APPROVED	5100031	2026-09-09 07:15:00.686465	\N	null
259	purchase_requisition	22	VENDOR_INVITED	5100024	2026-09-09 07:16:20.06935	\N	{"rfq_id": 13, "vendor_ids": [15]}
260	purchase_requisition	22	VENDOR_INVITED	5100024	2026-09-09 07:16:26.576805	\N	{"rfq_id": 13, "vendor_ids": [16]}
261	rfq	13	EMAIL_SENT	5100024	2026-09-09 07:16:41.47236	\N	{"email": "viratvenky207@gmail.com", "error": null, "vendor_id": 15}
262	rfq	13	EMAIL_SENT	5100024	2026-09-09 07:16:41.47236	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": null, "vendor_id": 16}
263	purchase_requisition	22	RFQ_SENT	5100024	2026-09-09 07:16:41.47236	\N	{"rfq_id": 13, "failed_count": 0, "vendor_count": 2}
264	purchase_requisition	22	QUOTATION_RECEIVED	5100024	2026-09-09 07:17:42.611169	\N	{"rfq_id": 13, "vendor_id": 15, "quotation_id": 16}
265	purchase_requisition	22	QUOTATION_RECEIVED	5100024	2026-09-09 07:18:35.943715	\N	{"rfq_id": 13, "vendor_id": 15, "quotation_id": 17}
266	purchase_requisition	22	VENDOR_SELECTED	5100024	2026-09-09 07:19:20.182116	\N	{"reason": "very reasonable", "vendor_id": 15, "quotation_id": 16}
267	rfq	11	EMAIL_SENT	5100024	2026-09-09 09:01:29.376345	\N	{"email": "viratvenky207@gmail.com", "error": null, "vendor_id": 15}
268	rfq	11	EMAIL_SENT	5100024	2026-09-09 09:01:29.376345	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": null, "vendor_id": 16}
269	purchase_requisition	21	RFQ_SENT	5100024	2026-09-09 09:01:29.376345	\N	{"rfq_id": 11, "failed_count": 0, "vendor_count": 2}
270	purchase_requisition	21	QUOTATION_RECEIVED	5100024	2026-09-09 11:45:21.98346	\N	{"rfq_id": 11, "vendor_id": 15, "quotation_id": 18}
271	rfq	8	EMAIL_SENT	5100024	2026-09-09 13:10:39.631332	\N	{"email": "viratvenky207@gmail.com", "error": null, "vendor_id": 15}
272	purchase_requisition	15	RFQ_SENT	5100024	2026-09-09 13:10:39.631332	\N	{"rfq_id": 8, "failed_count": 0, "vendor_count": 1, "selected_vendor_ids": [15]}
273	purchase_requisition	23	PR_REQUEST_RAISED	5100007	2026-09-09 13:14:08.734735	\N	null
274	purchase_requisition	23	SUBMITTED_FOR_APPROVAL	5100007	2026-09-09 13:14:51.541087	\N	null
275	purchase_requisition	23	PR_SENT_BACK_FOR_CLARIFICATION	5100031	2026-09-09 13:16:22.558879	\N	{"reason": "need some color reference samples"}
276	purchase_requisition	23	PR_RESUBMITTED	5100007	2026-09-09 13:16:50.468142	\N	{"reason": "need some color reference samples"}
277	purchase_requisition	23	PR_APPROVED	5100031	2026-09-09 13:17:35.59658	\N	{"reason": "overall good"}
278	purchase_requisition	23	VENDOR_INVITED	5100024	2026-09-09 13:18:26.0193	\N	{"rfq_id": 14, "vendor_ids": [15, 16]}
279	rfq	14	EMAIL_SENT	5100024	2026-09-09 13:18:36.178443	\N	{"email": "viratvenky207@gmail.com", "error": null, "vendor_id": 15}
280	rfq	14	EMAIL_SENT	5100024	2026-09-09 13:18:36.178443	\N	{"email": "jagadishreddypannala6281@gmail.com", "error": null, "vendor_id": 16}
281	purchase_requisition	23	RFQ_SENT	5100024	2026-09-09 13:18:36.178443	\N	{"rfq_id": 14, "failed_count": 0, "vendor_count": 2, "selected_vendor_ids": [15, 16]}
282	purchase_requisition	23	QUOTATION_RECEIVED	5100024	2026-09-09 13:19:31.114669	\N	{"rfq_id": 14, "vendor_id": 15, "quotation_id": 19}
283	purchase_requisition	23	VENDOR_SELECTED	5100024	2026-09-09 13:20:03.667807	\N	{"reason": "it is budget friendly", "vendor_id": 15, "quotation_id": 19}
284	vendor	17	CREATE	1	2026-09-17 12:03:18.420466	null	{"email": "galiv0758@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAACZ4322M", "currency_id": 1, "vendor_code": "ZCPL-K3328", "vendor_name": "ZOHO CORPORATION PRIVATE LIMITED - KARNATAKA", "phone_number": "90008090090", "payment_term_id": 3}
285	invoice	24	INVOICE_CREATED	5100031	2026-09-17 13:48:01.290953	\N	{"vendor_id": 15, "invoice_number": "AIN2627000969471"}
286	vendor	18	CREATE	1	2026-09-17 13:48:46.525345	null	{"email": "udemy@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAFFU9763M", "currency_id": 1, "vendor_code": "UIL1855", "vendor_name": "UDEMY INDIA LLP", "phone_number": "8270661145", "payment_term_id": 3}
287	vendor_category_mapping	1	CREATE	1	2026-09-17 13:48:54.325976	\N	{"vendor_id": 18, "department_id": 1, "business_requirement": "NEED OF LEARNING COURSES", "purchase_category_id": 2, "purpose_of_onboarding": null}
288	invoice	24	INVOICE_OCR_REVIEWED	5100031	2026-09-17 13:49:04.671937	\N	{"invoice_number": "AIN2627000969471"}
289	purchase_requisition	24	PR_REQUEST_RAISED	5100007	2026-09-18 05:35:21.030749	\N	null
290	invoice	25	INVOICE_CREATED	5100031	2026-09-18 05:35:35.406926	\N	{"vendor_id": 15, "invoice_number": "AIN2627000969471"}
291	purchase_requisition	24	SUBMITTED_FOR_APPROVAL	5100007	2026-09-18 05:37:12.487851	\N	null
292	purchase_requisition	24	PR_APPROVED	5100031	2026-09-18 05:37:53.861489	\N	null
293	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 05:38:36.277675	\N	{"available": false, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 0}
294	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 05:51:21.433873	\N	{"available": false, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 0}
295	vendor_onboarding_request	1	CREATED	5100024	2026-09-18 05:51:26.386603	\N	{"pr_id": 24, "department_id": 1, "purchase_category_id": 2, "requested_vendor_name": "ABC"}
296	purchase_requisition	24	VENDOR_ONBOARDING_REQUESTED	5100024	2026-09-18 05:51:26.386603	\N	{"onboarding_request_id": 1, "requested_vendor_name": "ABC"}
297	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 05:51:27.795884	\N	{"available": false, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 0}
298	purchase_requisition	15	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 06:05:07.76552	\N	{"available": false, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 0}
299	purchase_requisition	5	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 06:05:42.868074	\N	{"available": false, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 0}
300	purchase_requisition	15	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 06:17:27.846562	\N	{"available": false, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 0}
301	vendor	19	CREATE	5100024	2026-09-18 06:20:04.190563	null	{"email": "abc@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAFFU9763R", "currency_id": 1, "vendor_code": "A5007", "vendor_name": "ABC", "phone_number": "8270661125", "payment_term_id": 4}
302	vendor_address	15	CREATE	5100024	2026-09-18 06:20:06.17995	null	{"city": "Perintalmanna", "state": "Kerala", "country_id": 1, "is_primary": true, "postal_code": "679322", "address_type": "REGISTERED", "address_line1": "Thanneerpanthal, Pathaikkara", "address_line2": null}
303	vendor_category_mapping	2	CREATE	5100024	2026-09-18 06:20:06.98355	\N	{"vendor_id": 19, "department_id": 1, "business_requirement": "Need of cloud services", "purchase_category_id": 2, "purpose_of_onboarding": null}
304	invoice	25	INVOICE_OCR_REVIEWED	5100031	2026-09-18 06:20:47.491361	\N	{"invoice_number": "AIN2627000969471"}
305	invoice	25	INVOICE_SENT_FOR_APPROVAL	5100031	2026-09-18 06:21:19.193361	\N	{"status_code": "PENDING_APPROVAL", "approval_policy_id": 2, "invoice_approval_id": 3}
306	invoice	25	INVOICE_APPROVAL_STEP_DECISION	5100009	2026-09-18 06:30:25.754054	\N	{"comments": "Approved - verified vendor and amount", "decision": "APPROVED", "level_number": 1, "invoice_approval_id": 3}
307	invoice	25	INVOICE_APPROVED	5100009	2026-09-18 06:30:25.754054	\N	{"invoice_approval_id": 3}
308	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 06:32:12.954898	\N	{"available": false, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 0}
309	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 06:32:28.561102	\N	{"available": false, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 0}
310	purchase_requisition	25	PR_REQUEST_RAISED	5100007	2026-09-18 06:33:38.649511	\N	null
311	purchase_requisition	25	SUBMITTED_FOR_APPROVAL	5100007	2026-09-18 06:34:02.060568	\N	null
312	purchase_requisition	25	PR_APPROVED	5100031	2026-09-18 06:34:45.294918	\N	null
313	purchase_requisition	25	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 06:36:01.375341	\N	{"available": false, "department_id": 5, "purchase_category_id": 5, "eligible_vendor_count": 0}
314	vendor_onboarding_request	2	CREATED	5100024	2026-09-18 06:36:29.085651	\N	{"pr_id": 25, "department_id": 5, "purchase_category_id": 5, "requested_vendor_name": "XYZ"}
315	purchase_requisition	25	VENDOR_ONBOARDING_REQUESTED	5100024	2026-09-18 06:36:29.085651	\N	{"onboarding_request_id": 2, "requested_vendor_name": "XYZ"}
316	purchase_requisition	25	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 06:36:31.327514	\N	{"available": false, "department_id": 5, "purchase_category_id": 5, "eligible_vendor_count": 0}
317	purchase_requisition	25	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 06:36:46.722045	\N	{"available": false, "department_id": 5, "purchase_category_id": 5, "eligible_vendor_count": 0}
318	vendor	20	CREATE	5100024	2026-09-18 06:38:06.471727	null	{"email": "xyz@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAACZ4322P", "currency_id": 1, "vendor_code": "X0810", "vendor_name": "XYZ", "phone_number": "8270661148", "payment_term_id": 2}
319	vendor_address	16	CREATE	5100024	2026-09-18 06:38:09.324211	null	{"city": "Perintalmanna", "state": "Kerala", "country_id": 1, "is_primary": true, "postal_code": "679322", "address_type": "REGISTERED", "address_line1": "Thanneerpanthal, Pathaikkara", "address_line2": null}
320	vendor_category_mapping	3	CREATE	5100024	2026-09-18 06:38:10.391329	\N	{"vendor_id": 20, "department_id": 5, "business_requirement": "need of office supplies", "purchase_category_id": 5, "purpose_of_onboarding": null}
321	vendor_onboarding_request	2	INTAKE_STARTED	5100024	2026-09-18 06:38:11.311873	\N	{"vendor_id": 20, "engagement_id": 3, "vendor_created": true}
322	vendor_onboarding_request	2	PRE_SCREENED	5100024	2026-09-18 06:40:27.774986	\N	{"result": "PASS", "engagement_id": 3, "nda_recommended": false}
323	vendor_onboarding_request	2	COMPLETED	5100024	2026-09-18 06:40:34.229228	\N	{"vendor_id": 20, "engagement_id": 3}
324	purchase_requisition	25	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 06:40:38.836952	\N	{"available": false, "department_id": 5, "purchase_category_id": 5, "eligible_vendor_count": 0}
325	vendor	20	STATUS_CHANGE	5100024	2026-09-18 06:47:45.094777	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
326	purchase_requisition	25	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 06:47:54.198891	\N	{"available": true, "department_id": 5, "purchase_category_id": 5, "eligible_vendor_count": 1}
327	purchase_requisition	25	VENDOR_INVITED	5100024	2026-09-18 06:48:14.776479	\N	{"rfq_id": 15, "vendor_ids": [20]}
328	rfq	15	EMAIL_SENT	5100024	2026-09-18 06:48:33.15753	\N	{"email": "xyz@gmail.com", "error": null, "vendor_id": 20}
329	purchase_requisition	25	RFQ_SENT	5100024	2026-09-18 06:48:33.15753	\N	{"rfq_id": 15, "failed_count": 0, "vendor_count": 1, "selected_vendor_ids": [20]}
330	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 06:53:10.028562	\N	{"available": false, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 0}
331	vendor	18	STATUS_CHANGE	5100024	2026-09-18 06:53:34.980363	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
332	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 06:53:44.980025	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 1}
333	vendor	21	CREATE	5100024	2026-09-18 07:00:14.903617	null	{"email": "abc0758@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AGFHT9786C", "currency_id": 1, "vendor_code": "A3020", "vendor_name": "ABCC", "phone_number": "8270661128", "payment_term_id": 3}
334	vendor_address	17	CREATE	5100024	2026-09-18 07:00:18.407439	null	{"city": "Perintalmanna", "state": "Kerala", "country_id": 1, "is_primary": true, "postal_code": "679322", "address_type": "REGISTERED", "address_line1": "Thanneerpanthal, Pathaikkara", "address_line2": null}
335	vendor_category_mapping	4	CREATE	5100024	2026-09-18 07:00:18.807144	\N	{"vendor_id": 21, "department_id": 1, "business_requirement": "Need of cloud services", "purchase_category_id": 2, "purpose_of_onboarding": null}
336	vendor_onboarding_request	1	INTAKE_STARTED	5100024	2026-09-18 07:00:19.222361	\N	{"vendor_id": 21, "engagement_id": 4, "vendor_created": true}
337	vendor_onboarding_request	1	PRE_SCREENED	5100024	2026-09-18 07:00:25.357318	\N	{"result": "PASS", "engagement_id": 4, "nda_recommended": false}
338	vendor_onboarding_request	1	PRE_SCREENED	5100024	2026-09-18 07:01:09.637595	\N	{"result": "PASS", "engagement_id": 4, "nda_recommended": false}
339	vendor_onboarding_request	1	PRE_SCREENED	5100024	2026-09-18 07:03:32.354345	\N	{"result": "PASS", "engagement_id": 4, "nda_recommended": false}
340	vendor_onboarding_request	1	COMPLETED	5100024	2026-09-18 07:03:56.532492	\N	{"vendor_id": 21, "engagement_id": 4}
341	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 07:03:57.855432	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 1}
342	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 07:04:32.493956	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 1}
366	invoice	58	INVOICE_CREATED	5100031	2026-09-18 07:29:06.588458	\N	{"vendor_id": 15, "invoice_number": "AIN2627000969471"}
367	invoice	58	INVOICE_OCR_REVIEWED	5100031	2026-09-18 07:29:42.108355	\N	{"invoice_number": "AIN2627000969471"}
368	invoice	58	INVOICE_SENT_FOR_APPROVAL	5100031	2026-09-18 07:30:05.67361	\N	{"status_code": "PENDING_APPROVAL", "approval_policy_id": 2, "invoice_approval_id": 36}
369	vendor	54	CREATE	5100024	2026-09-18 07:41:39.28462	null	{"email": "zira34@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "DTMPM3599E", "currency_id": 1, "vendor_code": "ZTL1149", "vendor_name": "ZIRA TECH LASER", "phone_number": "8270661148", "payment_term_id": 3}
370	vendor_category_mapping	37	CREATE	5100024	2026-09-18 07:41:48.216957	\N	{"vendor_id": 54, "department_id": 1, "business_requirement": "Procurement of Zira Software licenses/subscription to support project management, issue tracking, task management, sprint planning, and team collaboration for software development projects.", "purchase_category_id": 2, "purpose_of_onboarding": null}
371	vendor	54	STATUS_CHANGE	5100024	2026-09-18 07:43:03.283973	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
372	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 07:43:29.860449	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
373	purchase_requisition	25	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 07:47:18.666238	\N	{"available": false, "department_id": 5, "purchase_category_id": 5, "eligible_vendor_count": 0}
374	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 07:47:28.082348	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
375	invoice	58	INVOICE_APPROVAL_STEP_DECISION	5100009	2026-09-18 09:01:28.298867	\N	{"comments": "approved", "decision": "APPROVED", "level_number": 1, "invoice_approval_id": 36}
376	invoice	58	INVOICE_APPROVED	5100009	2026-09-18 09:01:28.298867	\N	{"invoice_approval_id": 36}
377	invoice	58	INVOICE_READY_FOR_PAYMENT	5100009	2026-09-18 09:02:05.504553	{"status_code": "APPROVED"}	{"status_code": "READY_FOR_PAYMENT"}
378	purchase_requisition	25	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 10:30:18.183118	\N	{"available": false, "department_id": 5, "purchase_category_id": 5, "eligible_vendor_count": 0}
379	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 10:30:38.038344	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
380	vendor_onboarding_request	35	CREATED	5100024	2026-09-18 10:33:48.391586	\N	{"pr_id": 25, "department_id": 5, "purchase_category_id": 5, "requested_vendor_name": "ABC"}
381	purchase_requisition	25	VENDOR_ONBOARDING_REQUESTED	5100024	2026-09-18 10:33:48.391586	\N	{"onboarding_request_id": 35, "requested_vendor_name": "ABC"}
382	vendor	55	CREATE	5100024	2026-09-18 10:34:36.92508	null	{"email": "abc0758@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAACZ4322F", "currency_id": 1, "vendor_code": "A0440", "vendor_name": "ABC", "phone_number": "9270661145", "payment_term_id": 2}
383	vendor_address	51	CREATE	5100024	2026-09-18 10:34:40.088229	null	{"city": "Perintalmanna", "state": "Kerala", "country_id": 1, "is_primary": true, "postal_code": "679322", "address_type": "REGISTERED", "address_line1": "Thanneerpanthal, Pathaikkara", "address_line2": null}
384	vendor_category_mapping	38	CREATE	5100024	2026-09-18 10:34:42.233517	\N	{"vendor_id": 55, "department_id": 5, "business_requirement": "office appliance required", "purchase_category_id": 5, "purpose_of_onboarding": null}
385	vendor_onboarding_request	35	INTAKE_STARTED	5100024	2026-09-18 10:34:43.916519	\N	{"vendor_id": 55, "engagement_id": 38, "vendor_created": true}
386	vendor_onboarding_request	35	PRE_SCREENED	5100024	2026-09-18 10:34:53.650973	\N	{"result": "PASS", "engagement_id": 38, "nda_recommended": false}
387	vendor_onboarding_request	35	PRE_SCREENED	5100024	2026-09-18 10:35:10.471071	\N	{"result": "PASS", "engagement_id": 38, "nda_recommended": false}
388	vendor_onboarding_request	35	COMPLETED	5100024	2026-09-18 10:35:15.508134	\N	{"vendor_id": 55, "engagement_id": 38}
389	purchase_requisition	25	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 10:35:18.243059	\N	{"available": false, "department_id": 5, "purchase_category_id": 5, "eligible_vendor_count": 0}
390	vendor	55	STATUS_CHANGE	5100024	2026-09-18 10:36:03.796388	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
391	purchase_requisition	25	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 10:36:16.817052	\N	{"available": true, "department_id": 5, "purchase_category_id": 5, "eligible_vendor_count": 1}
392	purchase_requisition	25	VENDOR_INVITED	5100024	2026-09-18 10:36:38.446822	\N	{"rfq_id": 15, "vendor_ids": [55]}
393	purchase_requisition	25	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 10:36:57.776761	\N	{"available": true, "department_id": 5, "purchase_category_id": 5, "eligible_vendor_count": 1}
394	invoice	59	INVOICE_CREATED	5100007	2026-09-18 10:43:58.339503	\N	{"vendor_id": 15, "invoice_number": "AIN2627000969471"}
395	invoice	59	INVOICE_OCR_REVIEWED	5100007	2026-09-18 10:44:27.470036	\N	{"invoice_number": "AIN2627000969471"}
396	invoice	59	INVOICE_SENT_FOR_APPROVAL	5100007	2026-09-18 10:44:40.077202	\N	{"status_code": "PENDING_APPROVAL", "approval_policy_id": 2, "invoice_approval_id": 37}
397	purchase_requisition	25	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 10:47:20.787398	\N	{"available": true, "department_id": 5, "purchase_category_id": 5, "eligible_vendor_count": 1}
398	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 10:47:30.567777	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
399	invoice	59	INVOICE_SENT_BACK	5100021	2026-09-18 10:47:59.477655	\N	{"comments": "check and resubmit", "level_number": 1, "invoice_approval_id": 37}
430	purchase_requisition	25	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 11:17:32.103619	\N	{"available": true, "department_id": 5, "purchase_category_id": 5, "eligible_vendor_count": 1}
431	invoice	59	INVOICE_RESUBMITTED	5100007	2026-09-18 11:19:53.128602	\N	{"invoice_number": "AIN2627000969471"}
432	invoice	59	INVOICE_SENT_FOR_APPROVAL	5100007	2026-09-18 11:29:52.75462	\N	{"status_code": "PENDING_APPROVAL", "approval_policy_id": 2, "invoice_approval_id": 70}
433	invoice	59	INVOICE_APPROVAL_STEP_DECISION	5100021	2026-09-18 11:32:17.158277	\N	{"comments": "approved", "decision": "APPROVED", "level_number": 1, "invoice_approval_id": 70}
434	invoice	59	INVOICE_APPROVED	5100021	2026-09-18 11:32:17.158277	\N	{"invoice_approval_id": 70}
435	purchase_requisition	58	PR_REQUEST_RAISED	5100007	2026-09-18 11:44:22.36829	\N	null
436	purchase_requisition	58	SUBMITTED_FOR_APPROVAL	5100007	2026-09-18 11:45:04.382947	\N	null
437	purchase_requisition	58	PR_APPROVED	5100031	2026-09-18 11:53:20.172538	\N	{"reason": "approved"}
438	purchase_requisition	58	VENDOR_INVITED	5100009	2026-09-18 11:54:50.732722	\N	{"rfq_id": 49, "vendor_ids": [15]}
439	rfq	49	EMAIL_FAILED	5100009	2026-09-18 11:55:02.182857	\N	{"email": "viratvenky207@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 15}
440	rfq	49	EMAIL_FAILED	5100009	2026-09-18 11:55:26.083194	\N	{"email": "viratvenky207@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 15}
441	rfq	49	EMAIL_FAILED	5100009	2026-09-18 11:56:48.02184	\N	{"email": "kandukoori1919@gmail.com", "error": "SMTP is not configured: Missing required environment variable: SMTP_USERNAME", "vendor_id": 15}
442	rfq	49	EMAIL_FAILED	5100009	2026-09-18 12:03:25.861215	\N	{"email": "kandukoori1919@gmail.com", "error": "(550, b'5.4.5 Daily user sending limit exceeded. For more information on Gmail\\\\n5.4.5 sending limits go to\\\\n5.4.5  https://support.google.com/a/answer/166852 a92af1059eb24-144cddb4cf8sm4125962c88.1 - gsmtp')", "vendor_id": 15}
443	purchase_requisition	24	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 12:06:06.157899	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
444	purchase_requisition	24	VENDOR_INVITED	5100024	2026-09-18 12:06:21.584199	\N	{"rfq_id": 16, "vendor_ids": [18]}
445	rfq	16	EMAIL_SENT	5100024	2026-09-18 12:06:35.04935	\N	{"email": "udemy@gmail.com", "error": null, "vendor_id": 18}
446	purchase_requisition	24	RFQ_SENT	5100024	2026-09-18 12:06:35.04935	\N	{"rfq_id": 16, "failed_count": 0, "vendor_count": 1, "selected_vendor_ids": [18]}
447	purchase_requisition	58	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 12:07:14.245865	\N	{"available": false, "department_id": 1, "purchase_category_id": 1, "eligible_vendor_count": 0}
448	purchase_requisition	59	PR_REQUEST_RAISED	5100007	2026-09-18 12:08:17.102281	\N	null
449	purchase_requisition	59	SUBMITTED_FOR_APPROVAL	5100007	2026-09-18 12:09:34.813614	\N	null
450	purchase_requisition	59	PR_APPROVED	5100031	2026-09-18 12:10:10.157572	\N	null
451	purchase_requisition	59	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 12:10:46.804306	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
452	purchase_requisition	59	VENDOR_INVITED	5100024	2026-09-18 12:11:11.945816	\N	{"rfq_id": 50, "vendor_ids": [18]}
453	rfq	50	EMAIL_SENT	5100024	2026-09-18 12:11:22.379027	\N	{"email": "udemy@gmail.com", "error": null, "vendor_id": 18}
454	purchase_requisition	59	RFQ_SENT	5100024	2026-09-18 12:11:22.379027	\N	{"rfq_id": 50, "failed_count": 0, "vendor_count": 1, "selected_vendor_ids": [18]}
455	purchase_requisition	60	PR_REQUEST_RAISED	5100007	2026-09-18 12:37:12.027439	\N	null
456	purchase_requisition	60	SUBMITTED_FOR_APPROVAL	5100007	2026-09-18 12:38:34.418303	\N	null
457	purchase_requisition	60	PR_APPROVED	5100031	2026-09-18 12:39:39.96022	\N	{"reason": "approved"}
458	purchase_requisition	60	VENDOR_INVITED	5100009	2026-09-18 12:41:17.528385	\N	{"rfq_id": 51, "vendor_ids": [15]}
459	rfq	51	EMAIL_FAILED	5100009	2026-09-18 12:41:28.431506	\N	{"email": "kandukoori1919@gmail.com", "error": "(550, b'5.4.5 Daily user sending limit exceeded. For more information on Gmail\\\\n5.4.5 sending limits go to\\\\n5.4.5  https://support.google.com/a/answer/166852 5a478bee46e88-33c286d9654sm5256815eec.8 - gsmtp')", "vendor_id": 15}
460	purchase_requisition	60	VENDOR_INVITED	5100009	2026-09-18 12:41:45.690693	\N	{"rfq_id": 51, "vendor_ids": [18]}
461	rfq	51	EMAIL_FAILED	5100009	2026-09-18 12:41:54.47257	\N	{"email": "udemy@gmail.com", "error": "(550, b'5.4.5 Daily user sending limit exceeded. For more information on Gmail\\\\n5.4.5 sending limits go to\\\\n5.4.5  https://support.google.com/a/answer/166852 5a478bee46e88-33c286dc7dasm4997714eec.10 - gsmtp')", "vendor_id": 18}
462	purchase_requisition	59	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 12:43:37.490442	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
463	purchase_requisition	61	PR_REQUEST_RAISED	5100007	2026-09-18 12:45:46.139273	\N	null
464	purchase_requisition	61	SUBMITTED_FOR_APPROVAL	5100007	2026-09-18 12:46:13.226255	\N	null
465	purchase_requisition	61	PR_APPROVED	5100031	2026-09-18 12:46:48.762006	\N	null
466	purchase_requisition	61	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-18 12:47:34.970507	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
467	invoice	92	INVOICE_CREATED	5100007	2026-09-18 12:48:57.476021	\N	{"vendor_id": 15, "invoice_number": "AIN2627000969471"}
468	invoice	92	INVOICE_OCR_REVIEWED	5100007	2026-09-18 12:50:14.411412	\N	{"invoice_number": "AIN2627000969471"}
469	invoice	92	INVOICE_SENT_FOR_APPROVAL	5100007	2026-09-18 12:50:29.286365	\N	{"status_code": "PENDING_APPROVAL", "approval_policy_id": 2, "invoice_approval_id": 71}
470	invoice	92	INVOICE_APPROVAL_STEP_DECISION	5100009	2026-09-18 12:55:56.746131	\N	{"comments": "approved", "decision": "APPROVED", "level_number": 1, "invoice_approval_id": 71}
471	invoice	92	INVOICE_APPROVED	5100009	2026-09-18 12:55:56.746131	\N	{"invoice_approval_id": 71}
472	invoice	92	INVOICE_READY_FOR_PAYMENT	5100009	2026-09-18 12:58:57.33021	{"status_code": "APPROVED"}	{"status_code": "READY_FOR_PAYMENT"}
473	purchase_requisition	59	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 06:28:51.978748	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
474	purchase_requisition	59	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 10:14:24.923342	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
485	vendor	54	NDA_REQUIREMENT_DECIDED	5100024	2026-09-21 10:40:50.236576	\N	{"pr_id": 59, "nda_required": true, "department_id": 1, "purchase_category_id": 2}
486	vendor	54	NDA_EXISTING_CHECKED	5100024	2026-09-21 10:40:50.236576	\N	{"outcome": "NOT_FOUND"}
487	vendor_nda	1	NDA_GENERATED	5100024	2026-09-21 10:40:50.236576	\N	{"vendor_id": 54, "template_code": "STANDARD_NDA", "content_version": 1, "template_version": "1.0"}
488	vendor_nda	1	NDA_UPLOADED	5100024	2026-09-21 10:40:50.236576	\N	{"document_key": "ap/nda/generated/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf"}
489	vendor_nda	1	NDA_DOCUMENT_ACCESSED	5100024	2026-09-21 10:41:05.729636	\N	{"signed": false, "document_key": "ap/nda/generated/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf"}
490	vendor_nda	1	NDA_DOCUMENT_ACCESSED	5100024	2026-09-21 10:42:34.841541	\N	{"signed": false, "document_key": "ap/nda/generated/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf"}
491	vendor_nda	1	NDA_DOCUMENT_ACCESSED	5100024	2026-09-21 10:43:13.068398	\N	{"signed": false, "document_key": "ap/nda/generated/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf"}
492	vendor_nda	1	NDA_CONTENT_UPDATED	5100024	2026-09-21 10:43:24.553313	\N	{"status": "PENDING", "to_version": 2, "from_version": 1, "content_length": 1768}
493	vendor_nda	1	NDA_UPLOADED	5100024	2026-09-21 10:43:25.416471	\N	{"final": true, "document_key": "ap/nda/generated/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf", "content_version": 2}
494	vendor_nda	1	NDA_SEND_ATTEMPTED	5100024	2026-09-21 10:43:25.416471	\N	{"document_key": "ap/nda/generated/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf", "content_version": 2, "recipient_email": "zira34@gmail.com"}
495	vendor_nda	1	NDA_SENT	5100024	2026-09-21 10:43:25.416471	\N	{"recipient_email": "zira34@gmail.com"}
496	vendor_nda	1	NDA_DOCUMENT_ACCESSED	5100024	2026-09-21 10:43:49.665647	\N	{"signed": false, "document_key": "ap/nda/generated/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf"}
497	vendor_nda	1	NDA_SIGNED_DOCUMENT_UPLOADED	5100024	2026-09-21 10:46:00.259057	\N	{"from": "SENT", "uploaded_by": 5100024, "signed_document_key": "ap/nda/signed/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf"}
498	vendor_nda	1	NDA_SIGNED	5100024	2026-09-21 10:46:00.259057	\N	{"to": "SIGNED", "from": "SENT"}
499	vendor_nda	1	NDA_COMPLETED	5100024	2026-09-21 10:46:08.491775	\N	{"to": "COMPLETED", "from": "SIGNED"}
500	purchase_requisition	59	VENDOR_INVITED	5100024	2026-09-21 10:46:49.009408	\N	{"rfq_id": 50, "vendor_ids": [54]}
501	purchase_requisition	60	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 10:47:31.185151	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
502	vendor	15	NDA_REQUIREMENT_DECIDED	5100024	2026-09-21 10:48:18.120657	\N	{"pr_id": 60, "nda_required": true, "department_id": 1, "purchase_category_id": 2}
503	vendor	15	NDA_EXISTING_CHECKED	5100024	2026-09-21 10:48:18.120657	\N	{"outcome": "NOT_FOUND"}
504	vendor_nda	2	NDA_GENERATED	5100024	2026-09-21 10:48:18.120657	\N	{"vendor_id": 15, "template_code": "STANDARD_NDA", "content_version": 1, "template_version": "1.0"}
505	vendor_nda	2	NDA_UPLOADED	5100024	2026-09-21 10:48:18.120657	\N	{"document_key": "ap/nda/generated/2026/PR-000060/AWSIPL0336/NDA-PR-000060-AWSIPL0336-v1.0.pdf"}
506	goods_receipt	13	CREATE	script-test	2026-09-21 10:57:35.132301	null	{"po_id": 3, "file_path": null, "vendor_id": 15, "grn_number": "TEST-GRN-VERIFY-1", "receipt_date": "2026-09-21"}
507	goods_receipt	13	UPDATE	5100009	2026-09-21 11:05:22.948593	{"file_path": null}	{"file_path": "invoices/2026/09/1f4c7bd85c8f4449bc4ce69be5058d71_grn_test_doc.pdf"}
508	goods_receipt	14	CREATE	script-test	2026-09-21 11:17:28.73054	null	{"po_id": 3, "file_path": null, "vendor_id": 15, "grn_number": "TEST-GRN-VIA-ROUTE", "receipt_date": "2026-09-21"}
509	goods_receipt	13	UPDATE	script-test	2026-09-21 11:17:29.147975	{"file_path": "invoices/2026/09/1f4c7bd85c8f4449bc4ce69be5058d71_grn_test_doc.pdf"}	{"file_path": "invoices/2026/09/fd57c7102dbf4bb69c74b98e0296218e_grn_test_doc.pdf"}
510	goods_receipt	13	DELETE	script-cleanup	2026-09-21 11:17:49.51693	{"po_id": 3, "file_path": "invoices/2026/09/fd57c7102dbf4bb69c74b98e0296218e_grn_test_doc.pdf", "vendor_id": 15, "grn_number": "TEST-GRN-VERIFY-1", "receipt_date": "2026-09-21"}	null
511	goods_receipt	14	DELETE	script-cleanup	2026-09-21 11:17:49.875334	{"po_id": 3, "file_path": null, "vendor_id": 15, "grn_number": "TEST-GRN-VIA-ROUTE", "receipt_date": "2026-09-21"}	null
512	purchase_requisition	58	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 12:02:44.679798	\N	{"available": false, "department_id": 1, "purchase_category_id": 1, "eligible_vendor_count": 0}
513	purchase_requisition	59	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 12:02:54.828166	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
514	purchase_requisition	59	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 12:10:49.58245	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
515	purchase_requisition	61	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 12:11:14.458215	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
516	purchase_requisition	61	VENDOR_INVITED	5100024	2026-09-21 12:11:38.6639	\N	{"rfq_id": 52, "vendor_ids": [18, 54]}
517	vendor_nda	1	NDA_DOCUMENT_ACCESSED	5100024	2026-09-21 12:12:49.034211	\N	{"signed": false, "document_key": "ap/nda/generated/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf"}
518	vendor_nda	1	NDA_DOCUMENT_ACCESSED	5100024	2026-09-21 12:13:53.427817	\N	{"signed": false, "document_key": "ap/nda/generated/2026/PR-000059/ZTL1149/NDA-PR-000059-ZTL1149-v1.0.pdf"}
519	vendor_nda	1	NDA_EXPIRED	5100024	2026-09-21 12:14:14.142283	\N	{"to": "EXPIRED", "from": "COMPLETED"}
520	vendor	54	NDA_REQUIREMENT_DECIDED	5100024	2026-09-21 12:14:23.721896	\N	{"pr_id": 61, "nda_required": true, "department_id": 1, "purchase_category_id": 2}
521	vendor_nda	1	NDA_EXISTING_CHECKED	5100024	2026-09-21 12:14:23.721896	\N	{"outcome": "INVALID", "vendor_id": 54}
522	vendor_nda	3	NDA_GENERATED	5100024	2026-09-21 12:14:23.721896	\N	{"vendor_id": 54, "template_code": "STANDARD_NDA", "content_version": 1, "template_version": "1.0"}
523	vendor_nda	3	NDA_UPLOADED	5100024	2026-09-21 12:14:23.721896	\N	{"document_key": "ap/nda/generated/2026/PR-000061/ZTL1149/NDA-PR-000061-ZTL1149-v1.0.pdf"}
524	vendor_nda	3	NDA_DOCUMENT_ACCESSED	5100024	2026-09-21 12:14:42.075995	\N	{"signed": false, "document_key": "ap/nda/generated/2026/PR-000061/ZTL1149/NDA-PR-000061-ZTL1149-v1.0.pdf"}
525	purchase_requisition	61	QUOTATION_RECEIVED	5100024	2026-09-21 12:24:49.752595	\N	{"rfq_id": 52, "vendor_id": 18, "quotation_id": 20}
526	purchase_requisition	62	PR_REQUEST_RAISED	5100007	2026-09-21 12:42:06.463091	\N	null
527	purchase_requisition	62	SUBMITTED_FOR_APPROVAL	5100007	2026-09-21 12:42:48.583802	\N	null
528	purchase_requisition	62	PR_SENT_BACK_FOR_CLARIFICATION	5100031	2026-09-21 12:43:32.199097	\N	{"reason": "need some more detail information"}
529	purchase_requisition	62	PR_RESUBMITTED	5100007	2026-09-21 12:43:57.465463	\N	{"reason": "need some more detail information"}
530	purchase_requisition	62	PR_APPROVED	5100031	2026-09-21 12:44:38.639664	\N	null
531	purchase_requisition	62	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 12:51:26.691718	\N	{"available": false, "department_id": 1, "purchase_category_id": 1, "eligible_vendor_count": 0}
532	vendor_onboarding_request	68	CREATED	5100024	2026-09-21 12:52:19.719079	\N	{"pr_id": 62, "department_id": 1, "purchase_category_id": 1, "requested_vendor_name": "AQUA"}
533	purchase_requisition	62	VENDOR_ONBOARDING_REQUESTED	5100024	2026-09-21 12:52:19.719079	\N	{"onboarding_request_id": 68, "requested_vendor_name": "AQUA"}
534	purchase_requisition	62	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 12:52:20.530608	\N	{"available": false, "department_id": 1, "purchase_category_id": 1, "eligible_vendor_count": 0}
535	vendor	88	CREATE	5100024	2026-09-21 12:53:18.172866	null	{"email": "aqua0758@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAFFU9763G", "currency_id": 1, "vendor_code": "A2318", "vendor_name": "AQUA", "phone_number": "80008090090", "payment_term_id": 3}
536	vendor_address	84	CREATE	5100024	2026-09-21 12:53:19.123829	null	{"city": "Perintalmanna", "state": "Kerala", "country_id": 1, "is_primary": true, "postal_code": "679322", "address_type": "REGISTERED", "address_line1": "Thanneerpanthal, Pathaikkara", "address_line2": null}
537	vendor_category_mapping	71	CREATE	5100024	2026-09-21 12:53:19.591513	\N	{"vendor_id": 88, "department_id": 1, "business_requirement": "Required for Newly onboarded employees", "purchase_category_id": 1, "purpose_of_onboarding": null}
538	vendor_onboarding_request	68	INTAKE_STARTED	5100024	2026-09-21 12:53:19.999685	\N	{"vendor_id": 88, "engagement_id": 71, "vendor_created": true}
539	vendor_onboarding_request	68	PRE_SCREENED	5100024	2026-09-21 12:53:24.74293	\N	{"result": "PASS", "engagement_id": 71, "nda_recommended": false}
540	vendor_onboarding_request	68	PRE_SCREENED	5100024	2026-09-21 12:53:56.158619	\N	{"result": "PASS", "engagement_id": 71, "nda_recommended": false}
541	vendor_onboarding_request	68	COMPLETED	5100024	2026-09-21 12:54:10.853274	\N	{"vendor_id": 88, "engagement_id": 71}
542	purchase_requisition	62	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 12:54:12.38111	\N	{"available": false, "department_id": 1, "purchase_category_id": 1, "eligible_vendor_count": 0}
543	purchase_requisition	62	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 12:54:23.046807	\N	{"available": false, "department_id": 1, "purchase_category_id": 1, "eligible_vendor_count": 0}
544	vendor	88	STATUS_CHANGE	5100024	2026-09-21 12:54:35.117285	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
545	purchase_requisition	62	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 12:54:45.44212	\N	{"available": true, "department_id": 1, "purchase_category_id": 1, "eligible_vendor_count": 1}
546	purchase_requisition	62	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 13:03:39.755124	\N	{"available": true, "department_id": 1, "purchase_category_id": 1, "eligible_vendor_count": 1}
547	purchase_requisition	21	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 13:38:51.687691	\N	{"available": true, "department_id": 1, "purchase_category_id": 1, "eligible_vendor_count": 1}
548	purchase_requisition	63	PR_REQUEST_RAISED	5100007	2026-09-21 13:39:29.691516	\N	null
549	purchase_requisition	63	SUBMITTED_FOR_APPROVAL	5100007	2026-09-21 13:40:21.049089	\N	null
550	purchase_requisition	63	PR_APPROVED	5100031	2026-09-21 13:40:46.26203	\N	null
551	purchase_requisition	63	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 13:41:10.566707	\N	{"available": false, "department_id": 6, "purchase_category_id": 7, "eligible_vendor_count": 0}
552	vendor_onboarding_request	69	CREATED	5100024	2026-09-21 13:41:39.553719	\N	{"pr_id": 63, "department_id": 6, "purchase_category_id": 7, "requested_vendor_name": "Trainix"}
553	purchase_requisition	63	VENDOR_ONBOARDING_REQUESTED	5100024	2026-09-21 13:41:39.553719	\N	{"onboarding_request_id": 69, "requested_vendor_name": "Trainix"}
554	purchase_requisition	63	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 13:41:41.021558	\N	{"available": false, "department_id": 6, "purchase_category_id": 7, "eligible_vendor_count": 0}
555	vendor	89	CREATE	5100024	2026-09-21 13:42:55.35734	null	{"email": "trainx758@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAACZ4322N", "currency_id": 1, "vendor_code": "T1255", "vendor_name": "Trainx", "phone_number": "8270661128", "payment_term_id": 3}
556	vendor_address	85	CREATE	5100024	2026-09-21 13:42:56.102852	null	{"city": "Perintalmanna", "state": "Kerala", "country_id": 1, "is_primary": true, "postal_code": "679322", "address_type": "REGISTERED", "address_line1": "Thanneerpanthal, Pathaikkara", "address_line2": null}
557	vendor_category_mapping	72	CREATE	5100024	2026-09-21 13:42:56.744964	\N	{"vendor_id": 89, "department_id": 6, "business_requirement": "For Testing", "purchase_category_id": 7, "purpose_of_onboarding": null}
558	vendor_onboarding_request	69	INTAKE_STARTED	5100024	2026-09-21 13:42:57.131997	\N	{"vendor_id": 89, "engagement_id": 72, "vendor_created": true}
559	vendor_onboarding_request	69	PRE_SCREENED	5100024	2026-09-21 13:43:07.22435	\N	{"result": "PASS", "engagement_id": 72, "nda_recommended": false}
560	vendor_onboarding_request	69	PRE_SCREENED	5100024	2026-09-21 13:43:13.126392	\N	{"result": "PASS", "engagement_id": 72, "nda_recommended": false}
561	vendor_onboarding_request	69	COMPLETED	5100024	2026-09-21 13:48:16.458451	\N	{"vendor_id": 89, "engagement_id": 72}
562	purchase_requisition	63	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 13:48:18.020657	\N	{"available": false, "department_id": 6, "purchase_category_id": 7, "eligible_vendor_count": 0}
563	purchase_requisition	63	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 13:48:29.261531	\N	{"available": false, "department_id": 6, "purchase_category_id": 7, "eligible_vendor_count": 0}
564	vendor	89	STATUS_CHANGE	5100024	2026-09-21 13:48:46.945392	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
565	purchase_requisition	63	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 13:48:53.786044	\N	{"available": true, "department_id": 6, "purchase_category_id": 7, "eligible_vendor_count": 1}
566	purchase_requisition	63	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 13:49:02.426762	\N	{"available": true, "department_id": 6, "purchase_category_id": 7, "eligible_vendor_count": 1}
567	vendor	89	NDA_REQUIREMENT_DECIDED	5100024	2026-09-21 13:49:15.859394	\N	{"pr_id": 63, "nda_required": true, "department_id": 6, "purchase_category_id": 7}
568	vendor	89	NDA_EXISTING_CHECKED	5100024	2026-09-21 13:49:15.859394	\N	{"outcome": "NOT_FOUND"}
569	vendor_nda	4	NDA_GENERATED	5100024	2026-09-21 13:49:15.859394	\N	{"vendor_id": 89, "template_code": "STANDARD_NDA", "content_version": 1, "template_version": "1.0"}
570	vendor_nda	4	NDA_UPLOADED	5100024	2026-09-21 13:49:15.859394	\N	{"document_key": "ap/nda/generated/2026/PR-000063/T1255/NDA-PR-000063-T1255-v1.0.pdf"}
571	purchase_requisition	63	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 14:05:35.739092	\N	{"available": true, "department_id": 6, "purchase_category_id": 7, "eligible_vendor_count": 1}
572	purchase_requisition	63	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 14:05:47.604831	\N	{"available": true, "department_id": 6, "purchase_category_id": 7, "eligible_vendor_count": 1}
573	purchase_requisition	63	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 14:06:30.040535	\N	{"available": true, "department_id": 6, "purchase_category_id": 7, "eligible_vendor_count": 1}
574	vendor_nda	4	NDA_UPLOADED	5100024	2026-09-21 14:06:46.479555	\N	{"final": true, "document_key": "ap/nda/generated/2026/PR-000063/T1255/NDA-PR-000063-T1255-v1.0.pdf", "content_version": 1}
575	vendor_nda	4	NDA_SEND_ATTEMPTED	5100024	2026-09-21 14:06:46.479555	\N	{"document_key": "ap/nda/generated/2026/PR-000063/T1255/NDA-PR-000063-T1255-v1.0.pdf", "content_version": 1, "recipient_email": "trainx758@gmail.com"}
576	vendor_nda	4	NDA_SENT	5100024	2026-09-21 14:06:46.479555	\N	{"recipient_email": "trainx758@gmail.com"}
577	vendor_nda	4	NDA_DOCUMENT_ACCESSED	5100024	2026-09-21 14:07:06.557207	\N	{"signed": false, "document_key": "ap/nda/generated/2026/PR-000063/T1255/NDA-PR-000063-T1255-v1.0.pdf"}
578	purchase_requisition	63	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 14:07:12.996941	\N	{"available": true, "department_id": 6, "purchase_category_id": 7, "eligible_vendor_count": 1}
579	purchase_requisition	63	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 14:07:29.734569	\N	{"available": true, "department_id": 6, "purchase_category_id": 7, "eligible_vendor_count": 1}
580	purchase_requisition	63	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-21 14:07:51.703625	\N	{"available": true, "department_id": 6, "purchase_category_id": 7, "eligible_vendor_count": 1}
581	vendor_nda	4	NDA_COMPLETED	5100024	2026-09-21 14:08:09.851705	\N	{"to": "COMPLETED", "from": "SENT"}
582	purchase_requisition	63	VENDOR_INVITED	5100024	2026-09-21 14:08:19.815156	\N	{"rfq_id": 54, "vendor_ids": [89]}
583	purchase_requisition	64	PR_REQUEST_RAISED	5100007	2026-09-22 07:05:23.420988	\N	null
584	purchase_requisition	64	SUBMITTED_FOR_APPROVAL	5100007	2026-09-22 07:06:33.989307	\N	null
585	purchase_requisition	64	PR_APPROVED	5100031	2026-09-22 07:07:02.222862	\N	null
586	purchase_requisition	64	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-22 07:07:53.966508	\N	{"available": false, "department_id": 4, "purchase_category_id": 4, "eligible_vendor_count": 0}
587	vendor_onboarding_request	70	CREATED	5100024	2026-09-22 07:09:17.653142	\N	{"pr_id": 64, "department_id": 4, "purchase_category_id": 4, "requested_vendor_name": "FINRISK"}
588	purchase_requisition	64	VENDOR_ONBOARDING_REQUESTED	5100024	2026-09-22 07:09:17.653142	\N	{"onboarding_request_id": 70, "requested_vendor_name": "FINRISK"}
589	purchase_requisition	64	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-22 07:09:18.797219	\N	{"available": false, "department_id": 4, "purchase_category_id": 4, "eligible_vendor_count": 0}
590	vendor	90	CREATE	5100024	2026-09-22 07:10:22.93097	null	{"email": "finrisk@gmail.com", "status_id": 1, "country_id": 1, "pan_number": "AAACZ4322P", "currency_id": 1, "vendor_code": "F4023", "vendor_name": "FINRISK", "phone_number": "8270661146", "payment_term_id": 3}
591	vendor_address	86	CREATE	5100024	2026-09-22 07:10:23.868119	null	{"city": "Perintalmanna", "state": "Kerala", "country_id": 1, "is_primary": true, "postal_code": "679322", "address_type": "REGISTERED", "address_line1": "Thanneerpanthal, Pathaikkara", "address_line2": null}
592	vendor_category_mapping	73	CREATE	5100024	2026-09-22 07:10:24.327779	\N	{"vendor_id": 90, "department_id": 4, "business_requirement": "For Account Department", "purchase_category_id": 4, "purpose_of_onboarding": null}
593	vendor_onboarding_request	70	INTAKE_STARTED	5100024	2026-09-22 07:10:24.722668	\N	{"vendor_id": 90, "engagement_id": 73, "vendor_created": true}
594	vendor_onboarding_request	70	PRE_SCREENED	5100024	2026-09-22 07:10:30.774584	\N	{"result": "PASS", "engagement_id": 73, "nda_recommended": false}
595	vendor_onboarding_request	70	COMPLETED	5100024	2026-09-22 07:11:15.581335	\N	{"vendor_id": 90, "engagement_id": 73}
596	purchase_requisition	64	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-22 07:11:17.043131	\N	{"available": false, "department_id": 4, "purchase_category_id": 4, "eligible_vendor_count": 0}
597	purchase_requisition	64	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-22 07:11:41.815086	\N	{"available": false, "department_id": 4, "purchase_category_id": 4, "eligible_vendor_count": 0}
598	vendor	90	STATUS_CHANGE	1	2026-09-22 07:12:20.441889	{"status_id": 1}	{"status_id": 2, "status_code": "ACTIVE"}
599	purchase_requisition	64	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-22 07:13:00.890075	\N	{"available": true, "department_id": 4, "purchase_category_id": 4, "eligible_vendor_count": 1}
600	purchase_requisition	64	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-22 07:13:24.559044	\N	{"available": true, "department_id": 4, "purchase_category_id": 4, "eligible_vendor_count": 1}
601	purchase_requisition	64	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-22 07:13:29.253486	\N	{"available": true, "department_id": 4, "purchase_category_id": 4, "eligible_vendor_count": 1}
602	vendor	90	NDA_REQUIREMENT_DECIDED	5100024	2026-09-22 07:13:59.49745	\N	{"pr_id": 64, "nda_required": true, "department_id": 4, "purchase_category_id": 4}
603	vendor	90	NDA_EXISTING_CHECKED	5100024	2026-09-22 07:13:59.49745	\N	{"outcome": "NOT_FOUND"}
604	vendor_nda	5	NDA_GENERATED	5100024	2026-09-22 07:13:59.49745	\N	{"vendor_id": 90, "template_code": "STANDARD_NDA", "content_version": 1, "template_version": "1.0"}
605	vendor_nda	5	NDA_UPLOADED	5100024	2026-09-22 07:13:59.49745	\N	{"document_key": "ap/nda/generated/2026/PR-000064/F4023/NDA-PR-000064-F4023-v1.0.pdf"}
606	vendor_nda	5	NDA_DOCUMENT_ACCESSED	5100024	2026-09-22 07:14:13.580128	\N	{"signed": false, "document_key": "ap/nda/generated/2026/PR-000064/F4023/NDA-PR-000064-F4023-v1.0.pdf"}
607	purchase_requisition	64	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-22 07:14:31.241408	\N	{"available": true, "department_id": 4, "purchase_category_id": 4, "eligible_vendor_count": 1}
608	vendor_nda	5	NDA_UPLOADED	5100024	2026-09-22 07:14:58.967958	\N	{"final": true, "document_key": "ap/nda/generated/2026/PR-000064/F4023/NDA-PR-000064-F4023-v1.0.pdf", "content_version": 1}
609	vendor_nda	5	NDA_SEND_ATTEMPTED	5100024	2026-09-22 07:14:58.967958	\N	{"document_key": "ap/nda/generated/2026/PR-000064/F4023/NDA-PR-000064-F4023-v1.0.pdf", "content_version": 1, "recipient_email": "finrisk@gmail.com"}
610	vendor_nda	5	NDA_SENT	5100024	2026-09-22 07:14:58.967958	\N	{"recipient_email": "finrisk@gmail.com"}
611	vendor_nda	5	NDA_SIGNED_DOCUMENT_UPLOADED	5100024	2026-09-22 07:15:25.307657	\N	{"from": "SENT", "uploaded_by": 5100024, "signed_document_key": "ap/nda/signed/2026/PR-000064/F4023/NDA-PR-000064-F4023-v1.0.pdf"}
612	vendor_nda	5	NDA_SIGNED	5100024	2026-09-22 07:15:25.307657	\N	{"to": "SIGNED", "from": "SENT"}
613	vendor_nda	5	NDA_DOCUMENT_ACCESSED	5100024	2026-09-22 07:15:35.57382	\N	{"signed": true, "document_key": "ap/nda/signed/2026/PR-000064/F4023/NDA-PR-000064-F4023-v1.0.pdf"}
614	purchase_requisition	64	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-22 07:15:46.110851	\N	{"available": true, "department_id": 4, "purchase_category_id": 4, "eligible_vendor_count": 1}
615	vendor_nda	5	NDA_COMPLETED	5100024	2026-09-22 07:16:05.846149	\N	{"to": "COMPLETED", "from": "SIGNED"}
616	purchase_requisition	64	VENDOR_INVITED	5100024	2026-09-22 07:16:17.103207	\N	{"rfq_id": 55, "vendor_ids": [90]}
617	purchase_requisition	64	QUOTATION_RECEIVED	5100024	2026-09-22 07:19:38.283273	\N	{"rfq_id": 55, "vendor_id": 90, "quotation_id": 21}
618	rfq	55	EMAIL_SENT	5100024	2026-09-22 07:19:54.642896	\N	{"email": "finrisk@gmail.com", "error": null, "vendor_id": 90}
619	purchase_requisition	64	RFQ_SENT	5100024	2026-09-22 07:19:54.642896	\N	{"rfq_id": 55, "failed_count": 0, "vendor_count": 1, "selected_vendor_ids": [90]}
620	purchase_requisition	64	VENDOR_SELECTED	5100024	2026-09-22 07:21:13.212336	\N	{"reason": "more reasonable price", "vendor_id": 90, "quotation_id": 21}
621	vendor_nda	2	NDA_DOCUMENT_ACCESSED	5100024	2026-09-23 06:26:24.16404	\N	{"signed": false, "document_key": "ap/nda/generated/2026/PR-000060/AWSIPL0336/NDA-PR-000060-AWSIPL0336-v1.0.pdf"}
622	purchase_requisition	59	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-23 06:28:33.419127	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
623	vendor	18	NDA_REQUIREMENT_DECIDED	5100024	2026-09-23 06:29:37.346935	\N	{"pr_id": 59, "nda_required": true, "department_id": 1, "purchase_category_id": 2}
624	vendor	18	NDA_EXISTING_CHECKED	5100024	2026-09-23 06:29:37.346935	\N	{"outcome": "NOT_FOUND"}
625	vendor_nda	6	NDA_GENERATED	5100024	2026-09-23 06:29:37.346935	\N	{"vendor_id": 18, "template_code": "STANDARD_NDA", "content_version": 1, "template_version": "1.0"}
626	vendor_nda	6	NDA_UPLOADED	5100024	2026-09-23 06:29:37.346935	\N	{"document_key": "ap/nda/generated/2026/PR-000059/UIL1855/NDA-PR-000059-UIL1855-v1.0.pdf"}
627	vendor_nda	6	NDA_UPLOADED	5100024	2026-09-23 06:29:59.027955	\N	{"final": true, "document_key": "ap/nda/generated/2026/PR-000059/UIL1855/NDA-PR-000059-UIL1855-v1.0.pdf", "content_version": 1}
628	vendor_nda	6	NDA_SEND_ATTEMPTED	5100024	2026-09-23 06:29:59.027955	\N	{"document_key": "ap/nda/generated/2026/PR-000059/UIL1855/NDA-PR-000059-UIL1855-v1.0.pdf", "content_version": 1, "recipient_email": "udemy@gmail.com"}
629	vendor_nda	6	NDA_SENT	5100024	2026-09-23 06:29:59.027955	\N	{"recipient_email": "udemy@gmail.com"}
630	vendor_nda	6	NDA_COMPLETED	5100024	2026-09-23 06:30:31.06179	\N	{"to": "COMPLETED", "from": "SENT"}
631	purchase_requisition	59	QUOTATION_RECEIVED	5100024	2026-09-23 06:33:59.623712	\N	{"rfq_id": 50, "vendor_id": 18, "quotation_id": 22}
632	purchase_requisition	59	VENDOR_SELECTED	5100024	2026-09-23 06:34:35.671401	\N	{"reason": "good", "vendor_id": 18, "quotation_id": 22}
633	purchase_requisition	60	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-23 07:12:29.745393	\N	{"available": true, "department_id": 1, "purchase_category_id": 2, "eligible_vendor_count": 2}
634	rfq	52	EMAIL_SENT	5100024	2026-09-23 09:24:27.98227	\N	{"email": "udemy@gmail.com", "error": null, "vendor_id": 18}
635	purchase_requisition	61	RFQ_SENT	5100024	2026-09-23 09:24:27.98227	\N	{"rfq_id": 52, "failed_count": 0, "vendor_count": 1, "selected_vendor_ids": [18]}
636	purchase_requisition	61	VENDOR_SELECTED	5100024	2026-09-23 09:25:01.25349	\N	{"reason": "good", "vendor_id": 18, "quotation_id": 20}
637	purchase_requisition	65	PR_REQUEST_RAISED	5100007	2026-09-23 09:29:02.183971	\N	null
638	purchase_requisition	65	SUBMITTED_FOR_APPROVAL	5100007	2026-09-23 09:30:41.729756	\N	null
639	purchase_requisition	66	PR_REQUEST_RAISED	5100007	2026-09-23 09:31:49.784567	\N	null
640	purchase_requisition	66	SUBMITTED_FOR_APPROVAL	5100007	2026-09-23 09:32:39.547302	\N	null
641	purchase_requisition	66	PR_APPROVED	5100031	2026-09-23 09:33:36.644639	\N	null
642	purchase_requisition	66	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-23 09:37:55.512906	\N	{"available": true, "department_id": 1, "purchase_category_id": 1, "eligible_vendor_count": 1}
643	purchase_requisition	66	VENDOR_AVAILABILITY_CHECKED	5100024	2026-09-23 09:38:08.826545	\N	{"available": true, "department_id": 1, "purchase_category_id": 1, "eligible_vendor_count": 1}
644	purchase_requisition	66	VENDOR_INVITED	5100024	2026-09-23 09:38:11.542885	\N	{"rfq_id": 56, "vendor_ids": [88]}
645	rfq	56	EMAIL_SENT	5100024	2026-09-23 09:38:23.477224	\N	{"email": "aqua0758@gmail.com", "error": null, "vendor_id": 88}
646	purchase_requisition	66	RFQ_SENT	5100024	2026-09-23 09:38:23.477224	\N	{"rfq_id": 56, "failed_count": 0, "vendor_count": 1, "selected_vendor_ids": [88]}
647	purchase_requisition	66	QUOTATION_RECEIVED	5100024	2026-09-23 09:41:38.141121	\N	{"rfq_id": 56, "vendor_id": 88, "quotation_id": 23}
648	invoice	96	INVOICE_CREATED	5100007	2026-09-23 10:11:53.708333	\N	{"vendor_id": 15, "invoice_number": "AIN2627000969471"}
649	invoice	96	INVOICE_OCR_REVIEWED	5100007	2026-09-23 10:12:21.656381	\N	{"invoice_number": "AIN2627000969471"}
650	vendor_nda	2	NDA_DOCUMENT_ACCESSED	5100024	2026-09-23 10:17:26.699473	\N	{"signed": false, "document_key": "ap/nda/generated/2026/PR-000060/AWSIPL0336/NDA-PR-000060-AWSIPL0336-v1.0.pdf"}
651	invoice	99	INVOICE_CREATED	5100007	2026-09-23 12:21:09.664274	\N	{"vendor_id": 15, "invoice_number": "AIN2627000969471"}
652	invoice	99	INVOICE_OCR_REVIEWED	5100007	2026-09-23 12:22:54.425174	\N	{"invoice_number": "AIN2627000969471"}
653	invoice	100	INVOICE_CREATED	5100007	2026-09-23 14:16:03.222193	\N	{"vendor_id": 15, "invoice_number": "AIN2627000970001"}
654	invoice	100	INVOICE_OCR_REVIEWED	5100007	2026-09-23 14:16:24.393879	\N	{"invoice_number": "AIN2627000970001"}
\.


--
-- Data for Name: cdc_failure_log; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.cdc_failure_log (id, kafka_topic, kafka_partition, kafka_offset, entity_type, entity_key, operation, failure_type, error_message, raw_payload, retry_count, max_retries, status, created_at, updated_at) FROM stdin;
1	ums_cdc.ums.user	0	0	USER	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	r	MALFORMED_EVENT	No synced EOS employee/department yet for employee_uuid=0199bd8c-ef11-0ff0-1695-f2d12b5bcea2 (user_id=1, user_uuid=0199bd8c-ef11-0ff0-1695-f2d12b5bcea2)	{"mail": "admin.paves@pavestechnologies.com", "gender": "MALE", "contact": "+919100633231", "user_id": 1, "password": "$2b$12$WbNhPsi0Xfdms8Q/Z63/KewnNbEK6C4p021YVu/xWSLPCJCGqT8M2", "is_active": 1, "last_name": "Admin", "user_uuid": "0199bd8c-ef11-0ff0-1695-f2d12b5bcea2", "created_at": "2025-10-07T01:52:34Z", "first_name": "Paves", "updated_at": "2026-09-15T06:50:32Z", "employee_id": "5100001", "last_login_at": 1789455033000, "last_login_ip": "52.46.56.108", "password_last_updated": 1761716755000}	0	5	RESOLVED	2026-09-15 06:59:03.125575+00	2026-09-15 10:48:04.945549+00
2	ums_cdc.ums.user	0	1	USER	019e91fc-c2fd-0420-9cb1-29f5f71809bf	r	MISSING_DEPENDENCY	No synced EOS employee/department yet for employee_uuid=019e91fc-c2fd-0420-9cb1-29f5f71809bf (user_id=2, user_uuid=019e91fc-c2fd-0420-9cb1-29f5f71809bf)	{"mail": "system.internal@pavestechnologies.com", "gender": "MALE", "contact": "+919059364400", "user_id": 2, "password": "$2b$12$z7jwTtoz7uRuf9G2BckyqOJNz.eBYsyq69S9mkyqAsmUFsanUsp.u", "is_active": 1, "last_name": "Internal", "user_uuid": "019e91fc-c2fd-0420-9cb1-29f5f71809bf", "created_at": "2026-06-04T09:35:25Z", "first_name": "System", "updated_at": "2026-09-15T06:49:23Z", "employee_id": null, "last_login_at": 1789454964000, "last_login_ip": "15.158.25.203", "password_last_updated": 1780566091000}	0	5	RESOLVED	2026-09-15 06:59:03.477988+00	2026-09-15 10:48:05.353958+00
3	ums_cdc.ums.user	0	2	USER	019e8c6f-9735-2eba-21f1-56f5d79c3256	r	MALFORMED_EVENT	Could not parse employee_uuid='5100002' as a UUID	{"mail": "mohan.saladi@pavestechnologies.com", "gender": "MALE", "contact": "+919704622099", "user_id": 5100002, "password": "$2b$12$/mGnIu5s9rVQW7zXzd4JQubtNoee5BpGFWAHoFGJvIQbqJlsR2XaC", "is_active": 1, "last_name": "Saladi", "user_uuid": "019e8c6f-9735-2eba-21f1-56f5d79c3256", "created_at": "2026-06-03T07:45:51Z", "first_name": "Mohan Dharma Teja", "updated_at": "2026-06-09T07:14:30Z", "employee_id": "5100002", "last_login_at": 1780989271000, "last_login_ip": "52.46.56.79", "password_last_updated": 1780473198000}	2	5	RESOLVED	2026-09-15 06:59:03.765184+00	2026-09-15 07:29:54.584966+00
4	ums_cdc.ums.user	0	3	USER	019e8c6f-9746-823d-0fd1-572e7ff403c8	r	MALFORMED_EVENT	Could not parse employee_uuid='5100003' as a UUID	{"mail": "thejas.gajula@pavestechnologies.com", "gender": "MALE", "contact": "+917330925101", "user_id": 5100003, "password": "$2b$12$qFRBvzaV1verNDaBhS7tSOT58nVbS2gONvgXV71XsV8MFnn2gtefu", "is_active": 1, "last_name": "Gajula", "user_uuid": "019e8c6f-9746-823d-0fd1-572e7ff403c8", "created_at": "2026-06-03T07:45:51Z", "first_name": "Thejas", "updated_at": "2026-06-03T07:51:32Z", "employee_id": "5100003", "last_login_at": null, "last_login_ip": null, "password_last_updated": null}	2	5	RESOLVED	2026-09-15 06:59:04.071055+00	2026-09-15 07:29:55.142826+00
5	ums_cdc.ums.user	0	4	USER	019e8c6f-9754-6bc2-8378-21c15fe06b71	r	MALFORMED_EVENT	Could not parse employee_uuid='5100005' as a UUID	{"mail": "ajay.korada@pavestechnologies.com", "gender": "MALE", "contact": "+917981773241", "user_id": 5100005, "password": "$2b$12$1qYwbbTB8puM4JSDw5WE/.pFmUEUtsoRsuwZiwUqQr.T5.M7uEwJO", "is_active": 1, "last_name": "Korada", "user_uuid": "019e8c6f-9754-6bc2-8378-21c15fe06b71", "created_at": "2026-06-03T07:45:51Z", "first_name": "Ajay", "updated_at": "2026-09-10T06:28:24Z", "employee_id": "5100005", "last_login_at": 1789021705000, "last_login_ip": "52.46.56.79", "password_last_updated": 1780555505000}	2	5	RESOLVED	2026-09-15 06:59:04.363565+00	2026-09-15 07:29:55.785273+00
6	ums_cdc.ums.user	0	5	USER	019e8c6f-97d0-6379-9078-0ba22e4ec921	r	MALFORMED_EVENT	Could not parse employee_uuid='5100007' as a UUID	{"mail": "venkatesh.gali@pavestechnologies.com", "gender": "MALE", "contact": "+919876534689", "user_id": 5100007, "password": "$2b$12$dUUPvR1gBnCESZH17dq4zu4F7pO5.6k4SMRbsBMbab3PS8mUz1Sue", "is_active": 1, "last_name": "Gali", "user_uuid": "019e8c6f-97d0-6379-9078-0ba22e4ec921", "created_at": "2026-06-03T07:45:51Z", "first_name": "Venkatesh", "updated_at": "2026-09-09T13:16:34Z", "employee_id": "5100007", "last_login_at": 1788959795000, "last_login_ip": "52.46.56.79", "password_last_updated": 1781589689000}	2	5	RESOLVED	2026-09-15 06:59:04.706143+00	2026-09-15 07:29:56.462716+00
7	ums_cdc.ums.user	0	6	USER	019e8c6f-9763-00c7-b39c-59c56712443c	r	MALFORMED_EVENT	Could not parse employee_uuid='5100008' as a UUID	{"mail": "swarnaraj.alwala@pavestechnologies.com", "gender": "MALE", "contact": "+918096563083", "user_id": 5100008, "password": "$2b$12$dg0R5psjSQfPlZAV2XvhiukWHG76m7BCNzIaMdOzqK7LoMAKA73Ei", "is_active": 1, "last_name": "alwala", "user_uuid": "019e8c6f-9763-00c7-b39c-59c56712443c", "created_at": "2026-06-03T07:45:51Z", "first_name": "swaran raj", "updated_at": "2026-09-01T12:28:15Z", "employee_id": "5100008", "last_login_at": 1788265695000, "last_login_ip": "52.46.56.79", "password_last_updated": 1780479482000}	2	5	RESOLVED	2026-09-15 06:59:05.012853+00	2026-09-15 07:29:57.023478+00
8	ums_cdc.ums.user	0	7	USER	019e68eb-06b3-ae1c-03d8-27e8949646eb	r	MALFORMED_EVENT	Could not parse employee_uuid='5100009' as a UUID	{"mail": "jagadish.pannala@pavestechnologies.com", "gender": "MALE", "contact": "+919100633230", "user_id": 5100009, "password": "$2b$12$2NYQSIbUNwto565lDHOpEuWt46imB9hpbeTjDoUs4EpTkVDmIydDi", "is_active": 1, "last_name": "Pannala", "user_uuid": "019e68eb-06b3-ae1c-03d8-27e8949646eb", "created_at": "2026-05-27T10:36:52Z", "first_name": "Jagadish", "updated_at": "2026-09-11T13:14:42Z", "employee_id": "5100009", "last_login_at": 1789132483000, "last_login_ip": "52.46.56.79", "password_last_updated": 1788259703000}	2	5	RESOLVED	2026-09-15 06:59:05.301876+00	2026-09-15 07:29:57.584075+00
9	ums_cdc.ums.user	0	8	USER	019e8c6f-9772-c412-1177-4759698bb1d6	r	MALFORMED_EVENT	Could not parse employee_uuid='5100010' as a UUID	{"mail": "sathwik.perka@pavestechnologies.com", "gender": "MALE", "contact": "+916309586236", "user_id": 5100010, "password": "$2b$12$/o/OV//MkIXKbJPkm/8a/esnzcLMpNbfzeePXw6fEq6hnG8iT4V8S", "is_active": 1, "last_name": "Perka", "user_uuid": "019e8c6f-9772-c412-1177-4759698bb1d6", "created_at": "2026-06-03T07:45:51Z", "first_name": "Sathwik", "updated_at": "2026-09-11T05:58:48Z", "employee_id": "5100010", "last_login_at": 1789106328000, "last_login_ip": "52.46.56.79", "password_last_updated": 1780554935000}	2	5	RESOLVED	2026-09-15 06:59:05.560612+00	2026-09-15 07:29:58.08761+00
10	ums_cdc.ums.user	0	9	USER	019e8c6f-97dc-c1a8-8790-1a2e9d1184a9	r	MALFORMED_EVENT	Could not parse employee_uuid='5100011' as a UUID	{"mail": "sricharan.chilkuri@pavestechnologies.com", "gender": "MALE", "contact": "+919346639366", "user_id": 5100011, "password": "$2b$12$Fxj8tZnEwdrCNpppjHuauO0Kdl26ICClGZjE5w/EopgWeJnj9HSvW", "is_active": 1, "last_name": "Chilkuri", "user_uuid": "019e8c6f-97dc-c1a8-8790-1a2e9d1184a9", "created_at": "2026-06-03T07:45:51Z", "first_name": "Sri Charan", "updated_at": "2026-07-10T07:26:31Z", "employee_id": "5100011", "last_login_at": 1783668391000, "last_login_ip": "130.176.104.148", "password_last_updated": null}	2	5	RESOLVED	2026-09-15 06:59:05.860151+00	2026-09-15 07:29:58.690431+00
11	ums_cdc.ums.user	0	10	USER	019e8c6f-9781-e1a7-f161-74e0cfbca3cf	r	MALFORMED_EVENT	Could not parse employee_uuid='5100012' as a UUID	{"mail": "rangaswamy.dama@pavestechnologies.com", "gender": "MALE", "contact": "+919059582200", "user_id": 5100012, "password": "$2b$12$L7K7l5YU4e7hxGcwhrHNDOPUpfa87UU6m9DrOkfWYtFK.X8AHboMq", "is_active": 1, "last_name": "Dama", "user_uuid": "019e8c6f-9781-e1a7-f161-74e0cfbca3cf", "created_at": "2026-06-03T07:45:51Z", "first_name": "Rangaswamy", "updated_at": "2026-09-07T13:02:57Z", "employee_id": "5100012", "last_login_at": 1788786178000, "last_login_ip": "52.46.56.79", "password_last_updated": 1780479507000}	2	5	RESOLVED	2026-09-15 06:59:06.145417+00	2026-09-15 07:29:59.19774+00
12	ums_cdc.ums.user	0	11	USER	019e8c6f-978f-f260-6d86-d768ec44ba6d	r	MALFORMED_EVENT	Could not parse employee_uuid='5100013' as a UUID	{"mail": "ajay.bhukya@pavestechnologies.com", "gender": "MALE", "contact": "+919100633230", "user_id": 5100013, "password": "$2b$12$F2eQGDr0q29tvvVmDZ7jf.nlqljmXIp5Bb9I1/y/S1pCKH1MaCB5e", "is_active": 1, "last_name": "Bhukya", "user_uuid": "019e8c6f-978f-f260-6d86-d768ec44ba6d", "created_at": "2026-06-03T07:45:51Z", "first_name": "Ajay", "updated_at": "2026-09-11T05:21:43Z", "employee_id": "5100013", "last_login_at": 1789104104000, "last_login_ip": "3.172.97.201", "password_last_updated": 1780486778000}	2	5	RESOLVED	2026-09-15 06:59:06.427708+00	2026-09-15 07:29:59.869698+00
13	ums_cdc.ums.user	0	12	USER	019e8c42-2660-4fd6-56c8-14bc05878344	r	MALFORMED_EVENT	Could not parse employee_uuid='5100014' as a UUID	{"mail": "sindhu.yanala@pavestechnologies.com", "gender": "MALE", "contact": "+917396774639", "user_id": 5100014, "password": "$2b$12$6g7Hb5seacuo3r5p9vSEueGDTO1pItu/8xfYMc7WEvt59eH1tpCBS", "is_active": 1, "last_name": "Yanala", "user_uuid": "019e8c42-2660-4fd6-56c8-14bc05878344", "created_at": "2026-06-03T07:08:52Z", "first_name": "Sindhu", "updated_at": "2026-09-15T06:48:46Z", "employee_id": "5100014", "last_login_at": 1789454926000, "last_login_ip": "3.172.97.232", "password_last_updated": 1780472439000}	2	5	RESOLVED	2026-09-15 06:59:06.759606+00	2026-09-15 07:30:00.63858+00
14	ums_cdc.ums.user	0	13	USER	019e8c6f-979e-7e3e-8fa3-74a2d4a9edb6	r	MALFORMED_EVENT	Could not parse employee_uuid='5100015' as a UUID	{"mail": "rohit.lingarker@pavestechnologies.com", "gender": "MALE", "contact": "+917780294871", "user_id": 5100015, "password": "$2b$12$0jUqPMAgubc0QFdYLT38ouWhVOCqYWZM9nX4Z0Db8E9zU9ZTg15HO", "is_active": 1, "last_name": "lingarker", "user_uuid": "019e8c6f-979e-7e3e-8fa3-74a2d4a9edb6", "created_at": "2026-06-03T07:45:51Z", "first_name": "rohit", "updated_at": "2026-08-17T10:28:52Z", "employee_id": "5100015", "last_login_at": 1786962533000, "last_login_ip": "52.46.56.79", "password_last_updated": 1786948224000}	2	5	RESOLVED	2026-09-15 06:59:07.09411+00	2026-09-15 07:30:01.242355+00
15	ums_cdc.ums.user	0	14	USER	019e8c6f-97aa-842e-cde0-72514e55edda	r	MALFORMED_EVENT	Could not parse employee_uuid='5100017' as a UUID	{"mail": "vijayadurga.balada@pavestechnologies.com", "gender": "MALE", "contact": "+917995041766", "user_id": 5100017, "password": "$2b$12$AOpOtxwNqRb3qowxN0ojOepklSTYDqCrApdyGr94gYX5V2Q2.b2um", "is_active": 1, "last_name": "Balada", "user_uuid": "019e8c6f-97aa-842e-cde0-72514e55edda", "created_at": "2026-06-03T07:45:51Z", "first_name": "vijayadurga", "updated_at": "2026-08-06T13:11:07Z", "employee_id": "5100017", "last_login_at": 1786021868000, "last_login_ip": "52.46.56.79", "password_last_updated": 1786021845000}	2	5	RESOLVED	2026-09-15 06:59:07.47772+00	2026-09-15 07:30:01.885402+00
16	ums_cdc.ums.user	0	15	USER	019e8c6f-97b7-9061-d9d1-4704d264f454	r	MALFORMED_EVENT	Could not parse employee_uuid='5100020' as a UUID	{"mail": "aditya.bolli@pavestechnologies.com", "gender": "MALE", "contact": "+917815931935", "user_id": 5100020, "password": "$2b$12$cBmDqPHh3Z.EyNEEwvTKb.sgmJ/WV6UTvP2urHy77NaMwA5ivj/hK", "is_active": 1, "last_name": "Teja", "user_uuid": "019e8c6f-97b7-9061-d9d1-4704d264f454", "created_at": "2026-06-03T07:45:51Z", "first_name": "Bolli", "updated_at": "2026-09-15T06:51:05Z", "employee_id": "5100020", "last_login_at": 1789455065000, "last_login_ip": "52.46.56.79", "password_last_updated": 1780553635000}	2	5	RESOLVED	2026-09-15 06:59:07.773337+00	2026-09-15 07:30:02.608098+00
17	ums_cdc.ums.user	0	16	USER	019e8c6f-97c4-e62e-52b0-11b9e4816c88	r	MALFORMED_EVENT	Could not parse employee_uuid='5100021' as a UUID	{"mail": "niharika.kandukoori@pavestechnologies.com", "gender": "MALE", "contact": "+919502528882", "user_id": 5100021, "password": "$2b$12$tS05KC0GDRuumowBL5aPBePFCKjWF.APFfHm6XRj8CB4jtf6ydJ1i", "is_active": 1, "last_name": "Niharika", "user_uuid": "019e8c6f-97c4-e62e-52b0-11b9e4816c88", "created_at": "2026-06-03T07:45:51Z", "first_name": "Kandukoori", "updated_at": "2026-08-31T14:05:40Z", "employee_id": "5100021", "last_login_at": 1788185141000, "last_login_ip": "3.172.97.232", "password_last_updated": 1783590265000}	2	5	RESOLVED	2026-09-15 06:59:08.083423+00	2026-09-15 07:30:03.261187+00
18	ums_cdc.ums.user	0	17	USER	019e8c6f-97e9-b9ea-8af9-06af6c630bea	r	MALFORMED_EVENT	Could not parse employee_uuid='5100022' as a UUID	{"mail": "venipriya.p@pavestechnologies.com", "gender": "MALE", "contact": "+911226354762", "user_id": 5100022, "password": "$2b$12$7IHiNjsmtHpr7dF/0qA6PeSMWLJNNTSNEgFvHz9G1Wn0d4l5TZxPu", "is_active": 1, "last_name": "P", "user_uuid": "019e8c6f-97e9-b9ea-8af9-06af6c630bea", "created_at": "2026-06-03T07:45:51Z", "first_name": "Veni Priya", "updated_at": "2026-09-10T10:20:59Z", "employee_id": "5100022", "last_login_at": 1788944240000, "last_login_ip": "52.46.56.79", "password_last_updated": 1789035659000}	2	5	RESOLVED	2026-09-15 06:59:08.34536+00	2026-09-15 07:30:03.915766+00
19	ums_cdc.ums.user	0	18	USER	019e8c25-0e73-7147-6bda-1279601ab9b4	r	MALFORMED_EVENT	Could not parse employee_uuid='5100023' as a UUID	{"mail": "ramagopal.durgam@pavestechnologies.com", "gender": "MALE", "contact": "+918975645789", "user_id": 5100023, "password": "$2b$12$WbNhPsi0Xfdms8Q/Z63/KewnNbEK6C4p021YVu/xWSLPCJCGqT8M2", "is_active": 1, "last_name": "Durgam", "user_uuid": "019e8c25-0e73-7147-6bda-1279601ab9b4", "created_at": "2026-06-03T06:23:45Z", "first_name": "Rama", "updated_at": "2026-09-11T13:10:56Z", "employee_id": "5100023", "last_login_at": 1789132256000, "last_login_ip": "52.46.56.79", "password_last_updated": 1781862585000}	2	5	RESOLVED	2026-09-15 06:59:08.643531+00	2026-09-15 07:30:04.49705+00
20	ums_cdc.ums.user	0	19	USER	019e8c6f-9812-9a50-5d66-fa4dca42de44	r	MALFORMED_EVENT	Could not parse employee_uuid='5100024' as a UUID	{"mail": "rakesh.k@pavestechnologies.com", "gender": "MALE", "contact": "+919876543210", "user_id": 5100024, "password": "$2b$12$eU7RdFLfLWwNBdw6wDPl9uP1RPRKzH42aXMzmXUZrJ/8xZ3Fm9Gaa", "is_active": 1, "last_name": "k", "user_uuid": "019e8c6f-9812-9a50-5d66-fa4dca42de44", "created_at": "2026-06-03T07:45:51Z", "first_name": "rakesh", "updated_at": "2026-09-10T10:18:50Z", "employee_id": "5100024", "last_login_at": 1789035530000, "last_login_ip": "52.46.56.79", "password_last_updated": 1788781435000}	2	5	RESOLVED	2026-09-15 06:59:08.914011+00	2026-09-15 07:30:05.409806+00
21	ums_cdc.ums.user	0	20	USER	019e6973-3a4d-65c2-0b0a-34f73c5f18ee	r	MALFORMED_EVENT	Could not parse employee_uuid='5100025' as a UUID	{"mail": "sambi.eada@pavestechnologies.com", "gender": "MALE", "contact": "+14079699974", "user_id": 5100025, "password": "$2b$12$87W3ZykuVHlnTvn.tTYtIuoRBogCgWtFQ8QURq.Sx4VtxkvDiG1am", "is_active": 1, "last_name": "Eada", "user_uuid": "019e6973-3a4d-65c2-0b0a-34f73c5f18ee", "created_at": "2026-05-27T12:40:55Z", "first_name": "Sambi", "updated_at": "2026-06-03T07:52:40Z", "employee_id": "5100025", "last_login_at": null, "last_login_ip": null, "password_last_updated": null}	2	5	RESOLVED	2026-09-15 06:59:09.175598+00	2026-09-15 07:30:06.728315+00
22	ums_cdc.ums.user	0	21	USER	019e8c6f-97f6-9cd6-2ecb-9bb7916d5ec4	r	MALFORMED_EVENT	Could not parse employee_uuid='5100026' as a UUID	{"mail": "bindub.usarti@pavestechnologies.com", "gender": "MALE", "contact": "+918328561719", "user_id": 5100026, "password": "$2b$12$fV68KSCE8I2mpnp0OBNL2uN177wMEJN9ACWxdGunMp9PNy3Upy9Ha", "is_active": 1, "last_name": "U", "user_uuid": "019e8c6f-97f6-9cd6-2ecb-9bb7916d5ec4", "created_at": "2026-06-03T07:45:51Z", "first_name": "Bindu Bhargavi", "updated_at": "2026-09-03T07:23:38Z", "employee_id": "5100026", "last_login_at": 1788420218000, "last_login_ip": "52.46.56.79", "password_last_updated": 1787829296000}	2	5	RESOLVED	2026-09-15 06:59:09.483998+00	2026-09-15 07:30:07.583066+00
23	ums_cdc.ums.user	0	22	USER	019e8c6f-9805-1c42-431e-15c89a2f1ad8	r	MALFORMED_EVENT	Could not parse employee_uuid='5100027' as a UUID	{"mail": "kalasagar.p@pavestechnologies.com", "gender": "MALE", "contact": "+919381951224", "user_id": 5100027, "password": "$2b$12$ooeUbMKjnTk3.uFmpfops.IV6eT2pjMuAnCb8iMmGedcIwBXYylTW", "is_active": 1, "last_name": "P", "user_uuid": "019e8c6f-9805-1c42-431e-15c89a2f1ad8", "created_at": "2026-06-03T07:45:51Z", "first_name": "Kalasagar", "updated_at": "2026-09-04T07:19:16Z", "employee_id": "5100027", "last_login_at": 1788506356000, "last_login_ip": "15.158.2.75", "password_last_updated": 1787205428000}	2	5	RESOLVED	2026-09-15 06:59:09.987026+00	2026-09-15 07:30:08.150708+00
24	ums_cdc.ums.user	0	23	USER	a858c3ff-9b6c-412f-8c64-b6803f817d9a	r	MALFORMED_EVENT	Could not parse employee_uuid='5100028' as a UUID	{"mail": "test.user@pavestechnologies.com", "gender": "MALE", "contact": "7396777850", "user_id": 5100028, "password": "$2b$12$Iar/aTAi7D4bOGqBzORWvuHwcVwIULGgoCiToIr2uY4eZ4clXlsMK", "is_active": 1, "last_name": "user", "user_uuid": "a858c3ff-9b6c-412f-8c64-b6803f817d9a", "created_at": "2026-06-16T13:32:30Z", "first_name": "Test", "updated_at": "2026-06-16T13:32:30Z", "employee_id": "5100028", "last_login_at": null, "last_login_ip": null, "password_last_updated": null}	2	5	RESOLVED	2026-09-15 06:59:10.288007+00	2026-09-15 07:30:08.808896+00
25	ums_cdc.ums.user	0	24	USER	3e89bf42-0dda-4fc1-b67e-8590c0f444ad	r	MALFORMED_EVENT	Could not parse employee_uuid='5100029' as a UUID	{"mail": "sumiya.patha@pavestechnologies.com", "gender": "MALE", "contact": "+916302883868", "user_id": 5100029, "password": "$2b$12$Ps86jz3tdZc8Sm9PL9HmEOSI77S8SY6ooBmZqoNIbw5cJREA1pog2", "is_active": 1, "last_name": "pathan", "user_uuid": "3e89bf42-0dda-4fc1-b67e-8590c0f444ad", "created_at": "2026-06-16T13:32:30Z", "first_name": "sumiya", "updated_at": "2026-08-10T06:05:30Z", "employee_id": "5100029", "last_login_at": null, "last_login_ip": null, "password_last_updated": null}	2	5	RESOLVED	2026-09-15 06:59:10.700265+00	2026-09-15 07:30:09.637273+00
26	ums_cdc.ums.user	0	25	USER	ae79c79e-40f7-4126-935d-2a37f6195f9c	r	MALFORMED_EVENT	No synced EOS employee/department yet for employee_uuid=ae79c79e-40f7-4126-935d-2a37f6195f9c (user_id=5100030, user_uuid=ae79c79e-40f7-4126-935d-2a37f6195f9c)	{"mail": "sumu.pathan@pavestechnologies.com", "gender": "MALE", "contact": "+918989899998", "user_id": 5100030, "password": "$2b$12$DGWEMtMszUGYWiv3ZypB4O9hCLftx84ZjO7vwcg7RcHl0CjWJBUKC", "is_active": 1, "last_name": "pathan", "user_uuid": "ae79c79e-40f7-4126-935d-2a37f6195f9c", "created_at": "2026-06-16T13:32:30Z", "first_name": "sumu", "updated_at": "2026-08-10T06:04:27Z", "employee_id": "5100030", "last_login_at": null, "last_login_ip": null, "password_last_updated": null}	5	5	EXHAUSTED	2026-09-15 06:59:10.994501+00	2026-09-15 14:20:23.11127+00
27	ums_cdc.ums.user	0	26	USER	019fd71e-2bd0-af39-7b38-0b2a511b201e	r	MISSING_DEPENDENCY	No synced EOS employee/department yet for employee_uuid=019fd71e-2bd0-af39-7b38-0b2a511b201e (user_id=5100031, user_uuid=019fd71e-2bd0-af39-7b38-0b2a511b201e)	{"mail": "jagadishreddypannala6281@gmail.com", "gender": "MALE", "contact": "+919100633230", "user_id": 5100031, "password": "$2b$12$jJJQq3A6YBBsCgpRiyKvaeUNUSlUiSKCX4mFMA9ZTPr/eFi9BIp3i", "is_active": 1, "last_name": "Pannala", "user_uuid": "019fd71e-2bd0-af39-7b38-0b2a511b201e", "created_at": "2026-08-06T12:48:27Z", "first_name": "Jagadish Reddy", "updated_at": "2026-09-09T13:17:08Z", "employee_id": null, "last_login_at": 1788959829000, "last_login_ip": "52.46.56.79", "password_last_updated": 1787925918000}	5	5	EXHAUSTED	2026-09-15 06:59:11.30757+00	2026-09-15 14:20:23.762795+00
28	ums_cdc.ums.user	0	27	USER	01a06627-8abd-15cf-8a40-11027aacd5f9	r	MISSING_DEPENDENCY	No synced EOS employee/department yet for employee_uuid=01a06627-8abd-15cf-8a40-11027aacd5f9 (user_id=5100032, user_uuid=01a06627-8abd-15cf-8a40-11027aacd5f9)	{"mail": "Abhishek.g@pavestechnologies.com", "gender": "MALE", "contact": "919391732446", "user_id": 5100032, "password": "$2b$12$pT7s/5zfdH9LeF5WYsIZzu9ftmoIw8imNox7JMBUcMYeo/cnA8xdq", "is_active": 1, "last_name": "GUDA", "user_uuid": "01a06627-8abd-15cf-8a40-11027aacd5f9", "created_at": "2026-09-03T07:24:23Z", "first_name": "Abhishek", "updated_at": "2026-09-04T13:45:03Z", "employee_id": null, "last_login_at": 1788529503000, "last_login_ip": "52.46.56.79", "password_last_updated": 1788420552000}	5	5	EXHAUSTED	2026-09-15 06:59:11.616353+00	2026-09-15 14:20:24.416319+00
29	ums_cdc.ums.user	0	28	USER	01a06628-e2bb-6570-330f-e37ab1f83be8	r	MISSING_DEPENDENCY	No synced EOS employee/department yet for employee_uuid=01a06628-e2bb-6570-330f-e37ab1f83be8 (user_id=5100033, user_uuid=01a06628-e2bb-6570-330f-e37ab1f83be8)	{"mail": "Thrinadh.B@pavestechnologies.com", "gender": "MALE", "contact": "917671870668", "user_id": 5100033, "password": "$2b$12$J3vQpy0VoPfyMVSjyiGIluDjl/jfl0HvJZEld4L7fyp6px1zteVU6", "is_active": 1, "last_name": "Bhimavarapu", "user_uuid": "01a06628-e2bb-6570-330f-e37ab1f83be8", "created_at": "2026-09-03T07:25:51Z", "first_name": "Thrinadh Reddy", "updated_at": "2026-09-03T09:51:22Z", "employee_id": null, "last_login_at": 1788429082000, "last_login_ip": "127.0.0.1", "password_last_updated": 1788420697000}	5	5	EXHAUSTED	2026-09-15 06:59:11.925728+00	2026-09-15 14:20:24.908189+00
30	ums_cdc.ums.user	0	29	USER	01a0668d-084c-2662-6532-efd5dac60ff9	r	MISSING_DEPENDENCY	No synced EOS employee/department yet for employee_uuid=01a0668d-084c-2662-6532-efd5dac60ff9 (user_id=5100034, user_uuid=01a0668d-084c-2662-6532-efd5dac60ff9)	{"mail": "abhishek.guda12@gmail.com", "gender": "MALE", "contact": "+919391732446", "user_id": 5100034, "password": "$2b$12$w7sny.l0egD/34Ox7XXHbeXwmh0MeD0ninfqVd9Kc5bHEYnRVwnUK", "is_active": 1, "last_name": "G", "user_uuid": "01a0668d-084c-2662-6532-efd5dac60ff9", "created_at": "2026-09-03T09:15:14Z", "first_name": "abhishek", "updated_at": "2026-09-04T06:44:31Z", "employee_id": null, "last_login_at": 1788427044000, "last_login_ip": "127.0.0.1", "password_last_updated": 1788427038000}	5	5	EXHAUSTED	2026-09-15 06:59:12.295574+00	2026-09-15 14:20:25.455279+00
31	ums_cdc.ums.user	0	30	USER	01a066a2-3428-cb47-9c83-2c8834bcbc35	r	MISSING_DEPENDENCY	No synced EOS employee/department yet for employee_uuid=01a066a2-3428-cb47-9c83-2c8834bcbc35 (user_id=5100035, user_uuid=01a066a2-3428-cb47-9c83-2c8834bcbc35)	{"mail": "chinnuabhishek123@gmail.com", "gender": "MALE", "contact": "919391732446", "user_id": 5100035, "password": "$2b$12$sTJ7i1yFyH.SL6Xn.cO81OLitfcZxKV5fW8MZedi21wr0wq5uRNz.", "is_active": 1, "last_name": "Guda", "user_uuid": "01a066a2-3428-cb47-9c83-2c8834bcbc35", "created_at": "2026-09-03T09:38:21Z", "first_name": "abhi ", "updated_at": "2026-09-03T09:38:56Z", "employee_id": null, "last_login_at": 1788428337000, "last_login_ip": "127.0.0.1", "password_last_updated": null}	5	5	EXHAUSTED	2026-09-15 06:59:12.680347+00	2026-09-15 14:20:26.078081+00
32	ums_cdc.ums.user	0	31	USER	01a06b23-3a83-55f9-1781-87f59ad9f9be	r	MISSING_DEPENDENCY	No synced EOS employee/department yet for employee_uuid=01a06b23-3a83-55f9-1781-87f59ad9f9be (user_id=5100036, user_uuid=01a06b23-3a83-55f9-1781-87f59ad9f9be)	{"mail": "rangaswamy.dama@pavestachnologies.com", "gender": "MALE", "contact": "919391732446", "user_id": 5100036, "password": "$2b$12$7HFv6uxhdDc97Ew/IsrCMuCbdjmTsmbOZ4Zd53zmhJ1cvHNJ06GEu", "is_active": 1, "last_name": "swamy", "user_uuid": "01a06b23-3a83-55f9-1781-87f59ad9f9be", "created_at": "2026-09-04T06:37:46Z", "first_name": "Ranga", "updated_at": "2026-09-04T06:37:46Z", "employee_id": null, "last_login_at": null, "last_login_ip": null, "password_last_updated": null}	5	5	EXHAUSTED	2026-09-15 06:59:13.034789+00	2026-09-15 14:20:26.612001+00
33	ums_cdc.ums.user	0	32	USER	01a06b2a-1760-d68a-b150-64da98bd16d5	r	MISSING_DEPENDENCY	No synced EOS employee/department yet for employee_uuid=01a06b2a-1760-d68a-b150-64da98bd16d5 (user_id=5100037, user_uuid=01a06b2a-1760-d68a-b150-64da98bd16d5)	{"mail": "abhishek.guda123@gmail.com", "gender": "MALE", "contact": "919391732446", "user_id": 5100037, "password": "$2b$12$XtMJFZPIp5xvXMKG6MYgguypjAssjIvsmq93HhovgI5E/MA5oK/Mi", "is_active": 1, "last_name": "Guda", "user_uuid": "01a06b2a-1760-d68a-b150-64da98bd16d5", "created_at": "2026-09-04T06:45:16Z", "first_name": "abhishek", "updated_at": "2026-09-04T13:44:49Z", "employee_id": null, "last_login_at": 1788529490000, "last_login_ip": "52.46.56.79", "password_last_updated": null}	5	5	EXHAUSTED	2026-09-15 06:59:13.348333+00	2026-09-15 14:20:27.107517+00
34	ums_cdc.ums.user	0	33	USER	019e8c42-2660-4fd6-56c8-14bc05878344	u	MALFORMED_EVENT	Could not parse employee_uuid='5100014' as a UUID	{"mail": "sindhu.yanala@pavestechnologies.com", "gender": "MALE", "contact": "+917396774639", "user_id": 5100014, "password": "$2b$12$6g7Hb5seacuo3r5p9vSEueGDTO1pItu/8xfYMc7WEvt59eH1tpCBS", "is_active": 1, "last_name": "Yanala", "user_uuid": "019e8c42-2660-4fd6-56c8-14bc05878344", "created_at": "2026-06-03T07:08:52Z", "first_name": "Sindhu", "updated_at": "2026-09-15T06:57:26Z", "employee_id": "5100014", "last_login_at": 1789455447000, "last_login_ip": "3.172.97.232", "password_last_updated": 1780472439000}	2	5	RESOLVED	2026-09-15 06:59:13.664113+00	2026-09-15 07:30:15.490652+00
35	ums_cdc.ums.user	0	34	USER	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	u	MALFORMED_EVENT	No synced EOS employee/department yet for employee_uuid=0199bd8c-ef11-0ff0-1695-f2d12b5bcea2 (user_id=1, user_uuid=0199bd8c-ef11-0ff0-1695-f2d12b5bcea2)	{"mail": "admin.paves@pavestechnologies.com", "gender": "MALE", "contact": "+919100633231", "user_id": 1, "password": "$2b$12$WbNhPsi0Xfdms8Q/Z63/KewnNbEK6C4p021YVu/xWSLPCJCGqT8M2", "is_active": 1, "last_name": "Admin", "user_uuid": "0199bd8c-ef11-0ff0-1695-f2d12b5bcea2", "created_at": "2025-10-07T01:52:34Z", "first_name": "Paves", "updated_at": "2026-09-15T06:57:44Z", "employee_id": "5100001", "last_login_at": 1789455465000, "last_login_ip": "3.172.97.232", "password_last_updated": 1761716755000}	0	5	RESOLVED	2026-09-15 06:59:13.966542+00	2026-09-15 10:48:05.781597+00
36	ums_cdc.ums.user_role	0	0	USER_ROLE	user_id=1,role_id=1	r	MISSING_DEPENDENCY	Cannot resolve user_id=1/role_id=1 yet (user cached=False, role cached=True)	{"role_id": 1, "user_id": 1, "assigned_at": "2026-08-05T06:35:39Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:24.454694+00	2026-09-15 07:30:16.768178+00
37	ums_cdc.ums.user_role	0	1	USER_ROLE	user_id=1,role_id=2	r	MISSING_DEPENDENCY	Cannot resolve user_id=1/role_id=2 yet (user cached=False, role cached=True)	{"role_id": 2, "user_id": 1, "assigned_at": "2025-10-07T01:52:34Z", "assigned_by": null}	2	5	RESOLVED	2026-09-15 06:59:24.743538+00	2026-09-15 07:30:17.499399+00
38	ums_cdc.ums.user_role	0	2	USER_ROLE	user_id=1,role_id=3	r	MISSING_DEPENDENCY	Cannot resolve user_id=1/role_id=3 yet (user cached=False, role cached=True)	{"role_id": 3, "user_id": 1, "assigned_at": "2026-05-14T06:39:16Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:25.042582+00	2026-09-15 07:30:17.945942+00
39	ums_cdc.ums.user_role	0	3	USER_ROLE	user_id=1,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=1/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 1, "assigned_at": "2026-05-14T07:16:47Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:25.354387+00	2026-09-15 07:30:18.474831+00
40	ums_cdc.ums.user_role	0	4	USER_ROLE	user_id=1,role_id=7	r	MISSING_DEPENDENCY	Cannot resolve user_id=1/role_id=7 yet (user cached=False, role cached=True)	{"role_id": 7, "user_id": 1, "assigned_at": "2026-05-14T07:16:47Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:25.679602+00	2026-09-15 07:30:18.916567+00
41	ums_cdc.ums.user_role	0	5	USER_ROLE	user_id=1,role_id=30	r	MISSING_DEPENDENCY	Cannot resolve user_id=1/role_id=30 yet (user cached=False, role cached=True)	{"role_id": 30, "user_id": 1, "assigned_at": "2026-05-14T07:16:47Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:26.00155+00	2026-09-15 07:30:19.348594+00
42	ums_cdc.ums.user_role	0	6	USER_ROLE	user_id=1,role_id=31	r	MISSING_DEPENDENCY	Cannot resolve user_id=1/role_id=31 yet (user cached=False, role cached=True)	{"role_id": 31, "user_id": 1, "assigned_at": "2026-05-14T06:39:15Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:26.338368+00	2026-09-15 07:30:19.810665+00
43	ums_cdc.ums.user_role	0	7	USER_ROLE	user_id=1,role_id=32	r	MISSING_DEPENDENCY	Cannot resolve user_id=1/role_id=32 yet (user cached=False, role cached=True)	{"role_id": 32, "user_id": 1, "assigned_at": "2026-05-14T07:16:48Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:26.875997+00	2026-09-15 07:30:21.074174+00
44	ums_cdc.ums.user_role	0	8	USER_ROLE	user_id=1,role_id=33	r	MISSING_DEPENDENCY	Cannot resolve user_id=1/role_id=33 yet (user cached=False, role cached=True)	{"role_id": 33, "user_id": 1, "assigned_at": "2026-05-14T07:16:48Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:27.248402+00	2026-09-15 07:30:22.38376+00
45	ums_cdc.ums.user_role	0	9	USER_ROLE	user_id=1,role_id=37	r	MISSING_DEPENDENCY	Cannot resolve user_id=1/role_id=37 yet (user cached=False, role cached=True)	{"role_id": 37, "user_id": 1, "assigned_at": "2026-05-14T07:16:46Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:27.575334+00	2026-09-15 07:30:23.254854+00
46	ums_cdc.ums.user_role	0	10	USER_ROLE	user_id=1,role_id=39	r	MISSING_DEPENDENCY	Cannot resolve user_id=1/role_id=39 yet (user cached=False, role cached=True)	{"role_id": 39, "user_id": 1, "assigned_at": "2026-07-10T09:09:19Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:27.880788+00	2026-09-15 07:30:23.656736+00
47	ums_cdc.ums.user_role	0	11	USER_ROLE	user_id=2,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=2/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 2, "assigned_at": "2026-06-04T09:55:29Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:28.277676+00	2026-09-15 07:30:24.154133+00
48	ums_cdc.ums.user_role	0	12	USER_ROLE	user_id=2,role_id=38	r	MISSING_DEPENDENCY	Cannot resolve user_id=2/role_id=38 yet (user cached=False, role cached=True)	{"role_id": 38, "user_id": 2, "assigned_at": "2026-06-04T09:55:12Z", "assigned_by": null}	2	5	RESOLVED	2026-09-15 06:59:28.702375+00	2026-09-15 07:30:24.538982+00
49	ums_cdc.ums.user_role	0	13	USER_ROLE	user_id=5100002,role_id=1	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100002/role_id=1 yet (user cached=False, role cached=True)	{"role_id": 1, "user_id": 5100002, "assigned_at": "2026-06-03T07:54:50Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:29.011652+00	2026-09-15 07:30:24.94581+00
50	ums_cdc.ums.user_role	0	14	USER_ROLE	user_id=5100002,role_id=2	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100002/role_id=2 yet (user cached=False, role cached=True)	{"role_id": 2, "user_id": 5100002, "assigned_at": "2026-06-03T07:54:50Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:29.578221+00	2026-09-15 07:30:25.356719+00
51	ums_cdc.ums.user_role	0	15	USER_ROLE	user_id=5100002,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100002/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100002, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:29.895582+00	2026-09-15 07:30:25.819303+00
52	ums_cdc.ums.user_role	0	16	USER_ROLE	user_id=5100003,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100003/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100003, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:30.185291+00	2026-09-15 07:30:26.290696+00
53	ums_cdc.ums.user_role	0	17	USER_ROLE	user_id=5100005,role_id=3	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100005/role_id=3 yet (user cached=False, role cached=True)	{"role_id": 3, "user_id": 5100005, "assigned_at": "2026-06-04T06:41:49Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:30.471627+00	2026-09-15 07:30:26.716197+00
54	ums_cdc.ums.user_role	0	18	USER_ROLE	user_id=5100005,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100005/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100005, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:31.050766+00	2026-09-15 07:30:28.544515+00
55	ums_cdc.ums.user_role	0	19	USER_ROLE	user_id=5100005,role_id=39	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100005/role_id=39 yet (user cached=False, role cached=True)	{"role_id": 39, "user_id": 5100005, "assigned_at": "2026-07-08T07:10:29Z", "assigned_by": 5100012}	2	5	RESOLVED	2026-09-15 06:59:31.48063+00	2026-09-15 07:30:29.287976+00
56	ums_cdc.ums.user_role	0	20	USER_ROLE	user_id=5100005,role_id=45	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100005/role_id=45 yet (user cached=False, role cached=True)	{"role_id": 45, "user_id": 5100005, "assigned_at": "2026-08-20T07:08:58Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:31.913419+00	2026-09-15 07:30:29.848973+00
57	ums_cdc.ums.user_role	0	21	USER_ROLE	user_id=5100007,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100007/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100007, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:32.318273+00	2026-09-15 07:30:30.451517+00
58	ums_cdc.ums.user_role	0	22	USER_ROLE	user_id=5100007,role_id=33	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100007/role_id=33 yet (user cached=False, role cached=True)	{"role_id": 33, "user_id": 5100007, "assigned_at": "2026-06-09T07:14:50Z", "assigned_by": 5100002}	2	5	RESOLVED	2026-09-15 06:59:32.69688+00	2026-09-15 07:30:31.409433+00
59	ums_cdc.ums.user_role	0	23	USER_ROLE	user_id=5100007,role_id=45	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100007/role_id=45 yet (user cached=False, role cached=True)	{"role_id": 45, "user_id": 5100007, "assigned_at": "2026-08-20T07:07:14Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:33.01467+00	2026-09-15 07:30:33.146694+00
60	ums_cdc.ums.user_role	0	24	USER_ROLE	user_id=5100007,role_id=47	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100007/role_id=47 yet (user cached=False, role cached=True)	{"role_id": 47, "user_id": 5100007, "assigned_at": "2026-09-07T09:39:06Z", "assigned_by": 5100009}	2	5	RESOLVED	2026-09-15 06:59:33.330733+00	2026-09-15 07:30:33.853273+00
61	ums_cdc.ums.user_role	0	25	USER_ROLE	user_id=5100008,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100008/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100008, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:33.653047+00	2026-09-15 07:30:34.426262+00
62	ums_cdc.ums.user_role	0	26	USER_ROLE	user_id=5100008,role_id=31	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100008/role_id=31 yet (user cached=False, role cached=True)	{"role_id": 31, "user_id": 5100008, "assigned_at": "2026-06-04T06:38:05Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:33.941389+00	2026-09-15 07:30:34.845991+00
63	ums_cdc.ums.user_role	0	27	USER_ROLE	user_id=5100009,role_id=1	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100009/role_id=1 yet (user cached=False, role cached=True)	{"role_id": 1, "user_id": 5100009, "assigned_at": "2026-06-03T09:40:09Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:34.269983+00	2026-09-15 07:30:35.345132+00
64	ums_cdc.ums.user_role	0	28	USER_ROLE	user_id=5100009,role_id=2	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100009/role_id=2 yet (user cached=False, role cached=True)	{"role_id": 2, "user_id": 5100009, "assigned_at": "2026-06-03T10:35:11Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:34.586076+00	2026-09-15 07:30:36.006149+00
65	ums_cdc.ums.user_role	0	29	USER_ROLE	user_id=5100009,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100009/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100009, "assigned_at": "2026-05-27T10:36:52Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:34.939528+00	2026-09-15 07:30:36.50247+00
66	ums_cdc.ums.user_role	0	30	USER_ROLE	user_id=5100009,role_id=30	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100009/role_id=30 yet (user cached=False, role cached=True)	{"role_id": 30, "user_id": 5100009, "assigned_at": "2026-08-31T12:11:23Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:35.301027+00	2026-09-15 07:30:37.002159+00
67	ums_cdc.ums.user_role	0	31	USER_ROLE	user_id=5100009,role_id=31	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100009/role_id=31 yet (user cached=False, role cached=True)	{"role_id": 31, "user_id": 5100009, "assigned_at": "2026-06-05T06:36:50Z", "assigned_by": 5100009}	2	5	RESOLVED	2026-09-15 06:59:35.676236+00	2026-09-15 07:30:37.526793+00
68	ums_cdc.ums.user_role	0	32	USER_ROLE	user_id=5100009,role_id=43	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100009/role_id=43 yet (user cached=False, role cached=True)	{"role_id": 43, "user_id": 5100009, "assigned_at": "2026-08-18T13:38:20Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:35.981372+00	2026-09-15 07:30:38.068893+00
69	ums_cdc.ums.user_role	0	33	USER_ROLE	user_id=5100009,role_id=49	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100009/role_id=49 yet (user cached=False, role cached=True)	{"role_id": 49, "user_id": 5100009, "assigned_at": "2026-09-07T11:25:21Z", "assigned_by": 5100009}	2	5	RESOLVED	2026-09-15 06:59:36.280739+00	2026-09-15 07:30:38.881504+00
70	ums_cdc.ums.user_role	0	34	USER_ROLE	user_id=5100010,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100010/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100010, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:36.573044+00	2026-09-15 07:30:39.438976+00
71	ums_cdc.ums.user_role	0	35	USER_ROLE	user_id=5100010,role_id=7	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100010/role_id=7 yet (user cached=False, role cached=True)	{"role_id": 7, "user_id": 5100010, "assigned_at": "2026-06-04T06:37:46Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:36.907885+00	2026-09-15 07:30:40.74685+00
72	ums_cdc.ums.user_role	0	36	USER_ROLE	user_id=5100010,role_id=30	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100010/role_id=30 yet (user cached=False, role cached=True)	{"role_id": 30, "user_id": 5100010, "assigned_at": "2026-06-04T06:38:18Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:37.229286+00	2026-09-15 07:30:42.106266+00
73	ums_cdc.ums.user_role	0	37	USER_ROLE	user_id=5100011,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100011/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100011, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:37.516358+00	2026-09-15 07:30:42.639762+00
74	ums_cdc.ums.user_role	0	38	USER_ROLE	user_id=5100012,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100012/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100012, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:37.833282+00	2026-09-15 07:30:43.131737+00
75	ums_cdc.ums.user_role	0	39	USER_ROLE	user_id=5100012,role_id=32	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100012/role_id=32 yet (user cached=False, role cached=True)	{"role_id": 32, "user_id": 5100012, "assigned_at": "2026-08-25T13:03:11Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:38.129711+00	2026-09-15 07:30:43.509626+00
76	ums_cdc.ums.user_role	0	40	USER_ROLE	user_id=5100012,role_id=33	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100012/role_id=33 yet (user cached=False, role cached=True)	{"role_id": 33, "user_id": 5100012, "assigned_at": "2026-08-25T13:03:56Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:38.469858+00	2026-09-15 07:30:43.943105+00
77	ums_cdc.ums.user_role	0	41	USER_ROLE	user_id=5100013,role_id=2	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100013/role_id=2 yet (user cached=False, role cached=True)	{"role_id": 2, "user_id": 5100013, "assigned_at": "2026-06-03T11:41:01Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:38.948024+00	2026-09-15 07:30:44.498089+00
78	ums_cdc.ums.user_role	0	42	USER_ROLE	user_id=5100013,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100013/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100013, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:39.365472+00	2026-09-15 07:30:45.062158+00
79	ums_cdc.ums.user_role	0	43	USER_ROLE	user_id=5100013,role_id=30	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100013/role_id=30 yet (user cached=False, role cached=True)	{"role_id": 30, "user_id": 5100013, "assigned_at": "2026-08-31T09:12:56Z", "assigned_by": 5100013}	2	5	RESOLVED	2026-09-15 06:59:39.802165+00	2026-09-15 07:30:45.634101+00
80	ums_cdc.ums.user_role	0	44	USER_ROLE	user_id=5100013,role_id=31	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100013/role_id=31 yet (user cached=False, role cached=True)	{"role_id": 31, "user_id": 5100013, "assigned_at": "2026-07-09T10:06:12Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:40.364527+00	2026-09-15 07:30:46.067926+00
81	ums_cdc.ums.user_role	0	45	USER_ROLE	user_id=5100014,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100014/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100014, "assigned_at": "2026-06-03T07:08:52Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:40.855356+00	2026-09-15 07:30:46.46147+00
82	ums_cdc.ums.user_role	0	46	USER_ROLE	user_id=5100014,role_id=30	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100014/role_id=30 yet (user cached=False, role cached=True)	{"role_id": 30, "user_id": 5100014, "assigned_at": "2026-07-30T11:22:39Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:41.167436+00	2026-09-15 07:30:46.989168+00
83	ums_cdc.ums.user_role	0	47	USER_ROLE	user_id=5100015,role_id=3	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100015/role_id=3 yet (user cached=False, role cached=True)	{"role_id": 3, "user_id": 5100015, "assigned_at": "2026-08-17T06:29:32Z", "assigned_by": 5100009}	2	5	RESOLVED	2026-09-15 06:59:41.56934+00	2026-09-15 07:30:47.473921+00
84	ums_cdc.ums.user_role	0	48	USER_ROLE	user_id=5100015,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100015/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100015, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:41.855353+00	2026-09-15 07:30:47.965118+00
85	ums_cdc.ums.user_role	0	49	USER_ROLE	user_id=5100015,role_id=30	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100015/role_id=30 yet (user cached=False, role cached=True)	{"role_id": 30, "user_id": 5100015, "assigned_at": "2026-07-30T11:21:38Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:42.15495+00	2026-09-15 07:30:48.486303+00
86	ums_cdc.ums.user_role	0	50	USER_ROLE	user_id=5100017,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100017/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100017, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:42.436502+00	2026-09-15 07:30:48.941688+00
87	ums_cdc.ums.user_role	0	51	USER_ROLE	user_id=5100017,role_id=30	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100017/role_id=30 yet (user cached=False, role cached=True)	{"role_id": 30, "user_id": 5100017, "assigned_at": "2026-06-03T09:57:25Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:42.874423+00	2026-09-15 07:30:49.438921+00
88	ums_cdc.ums.user_role	0	52	USER_ROLE	user_id=5100020,role_id=1	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100020/role_id=1 yet (user cached=False, role cached=True)	{"role_id": 1, "user_id": 5100020, "assigned_at": "2026-07-09T07:50:35Z", "assigned_by": 5100020}	2	5	RESOLVED	2026-09-15 06:59:43.263707+00	2026-09-15 07:30:50.164645+00
89	ums_cdc.ums.user_role	0	53	USER_ROLE	user_id=5100020,role_id=2	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100020/role_id=2 yet (user cached=False, role cached=True)	{"role_id": 2, "user_id": 5100020, "assigned_at": "2026-07-08T10:30:49Z", "assigned_by": 5100012}	2	5	RESOLVED	2026-09-15 06:59:43.631531+00	2026-09-15 07:30:51.18008+00
90	ums_cdc.ums.user_role	0	54	USER_ROLE	user_id=5100020,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100020/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100020, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:43.9449+00	2026-09-15 07:30:51.803894+00
91	ums_cdc.ums.user_role	0	55	USER_ROLE	user_id=5100020,role_id=43	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100020/role_id=43 yet (user cached=False, role cached=True)	{"role_id": 43, "user_id": 5100020, "assigned_at": "2026-08-27T11:10:37Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:44.280623+00	2026-09-15 07:30:53.175155+00
92	ums_cdc.ums.user_role	0	56	USER_ROLE	user_id=5100021,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100021/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100021, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:44.571366+00	2026-09-15 07:30:53.7085+00
93	ums_cdc.ums.user_role	0	57	USER_ROLE	user_id=5100022,role_id=3	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100022/role_id=3 yet (user cached=False, role cached=True)	{"role_id": 3, "user_id": 5100022, "assigned_at": "2026-06-03T09:11:04Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:44.899699+00	2026-09-15 07:30:54.262549+00
94	ums_cdc.ums.user_role	0	58	USER_ROLE	user_id=5100022,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100022/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100022, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:45.219841+00	2026-09-15 07:30:54.903184+00
95	ums_cdc.ums.user_role	0	59	USER_ROLE	user_id=5100022,role_id=39	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100022/role_id=39 yet (user cached=False, role cached=True)	{"role_id": 39, "user_id": 5100022, "assigned_at": "2026-09-10T10:20:26Z", "assigned_by": 5100013}	2	5	RESOLVED	2026-09-15 06:59:45.508844+00	2026-09-15 07:30:55.379838+00
96	ums_cdc.ums.user_role	0	60	USER_ROLE	user_id=5100022,role_id=40	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100022/role_id=40 yet (user cached=False, role cached=True)	{"role_id": 40, "user_id": 5100022, "assigned_at": "2026-07-08T12:48:37Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:46.120331+00	2026-09-15 07:30:55.836729+00
97	ums_cdc.ums.user_role	0	61	USER_ROLE	user_id=5100022,role_id=41	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100022/role_id=41 yet (user cached=False, role cached=True)	{"role_id": 41, "user_id": 5100022, "assigned_at": "2026-09-10T10:20:26Z", "assigned_by": 5100013}	2	5	RESOLVED	2026-09-15 06:59:46.430551+00	2026-09-15 07:30:56.472796+00
98	ums_cdc.ums.user_role	0	62	USER_ROLE	user_id=5100023,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100023/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100023, "assigned_at": "2026-06-03T06:23:47Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:46.836542+00	2026-09-15 07:30:56.993362+00
99	ums_cdc.ums.user_role	0	63	USER_ROLE	user_id=5100023,role_id=31	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100023/role_id=31 yet (user cached=False, role cached=True)	{"role_id": 31, "user_id": 5100023, "assigned_at": "2026-06-03T09:11:14Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:47.147588+00	2026-09-15 07:30:57.643775+00
100	ums_cdc.ums.user_role	0	64	USER_ROLE	user_id=5100024,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100024/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100024, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	2	5	RESOLVED	2026-09-15 06:59:47.452518+00	2026-09-15 07:30:58.11341+00
101	ums_cdc.ums.user_role	0	65	USER_ROLE	user_id=5100024,role_id=41	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100024/role_id=41 yet (user cached=False, role cached=True)	{"role_id": 41, "user_id": 5100024, "assigned_at": "2026-07-08T12:48:18Z", "assigned_by": 1}	0	5	RESOLVED	2026-09-15 06:59:47.768751+00	2026-09-15 07:41:07.616639+00
102	ums_cdc.ums.user_role	0	66	USER_ROLE	user_id=5100024,role_id=42	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100024/role_id=42 yet (user cached=False, role cached=True)	{"role_id": 42, "user_id": 5100024, "assigned_at": "2026-09-08T06:39:06Z", "assigned_by": 5100009}	0	5	RESOLVED	2026-09-15 06:59:48.071145+00	2026-09-15 07:41:08.186971+00
103	ums_cdc.ums.user_role	0	67	USER_ROLE	user_id=5100024,role_id=49	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100024/role_id=49 yet (user cached=False, role cached=True)	{"role_id": 49, "user_id": 5100024, "assigned_at": "2026-09-07T11:43:36Z", "assigned_by": 5100009}	0	5	RESOLVED	2026-09-15 06:59:48.474593+00	2026-09-15 07:41:08.75665+00
104	ums_cdc.ums.user_role	0	68	USER_ROLE	user_id=5100025,role_id=1	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100025/role_id=1 yet (user cached=False, role cached=True)	{"role_id": 1, "user_id": 5100025, "assigned_at": "2026-05-28T09:01:07Z", "assigned_by": 1}	0	5	RESOLVED	2026-09-15 06:59:48.826991+00	2026-09-15 07:41:09.216353+00
105	ums_cdc.ums.user_role	0	69	USER_ROLE	user_id=5100025,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100025/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100025, "assigned_at": "2026-05-27T12:40:56Z", "assigned_by": 1}	0	5	RESOLVED	2026-09-15 06:59:49.152905+00	2026-09-15 07:41:09.983133+00
106	ums_cdc.ums.user_role	0	70	USER_ROLE	user_id=5100025,role_id=30	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100025/role_id=30 yet (user cached=False, role cached=True)	{"role_id": 30, "user_id": 5100025, "assigned_at": "2026-05-28T09:01:07Z", "assigned_by": 1}	0	5	RESOLVED	2026-09-15 06:59:49.458391+00	2026-09-15 07:41:11.056488+00
107	ums_cdc.ums.user_role	0	71	USER_ROLE	user_id=5100025,role_id=31	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100025/role_id=31 yet (user cached=False, role cached=True)	{"role_id": 31, "user_id": 5100025, "assigned_at": "2026-05-28T09:01:07Z", "assigned_by": 1}	0	5	RESOLVED	2026-09-15 06:59:49.76638+00	2026-09-15 07:41:12.295672+00
108	ums_cdc.ums.user_role	0	72	USER_ROLE	user_id=5100026,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100026/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100026, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	0	5	RESOLVED	2026-09-15 06:59:50.156304+00	2026-09-15 07:41:13.833861+00
109	ums_cdc.ums.user_role	0	73	USER_ROLE	user_id=5100026,role_id=46	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100026/role_id=46 yet (user cached=False, role cached=True)	{"role_id": 46, "user_id": 5100026, "assigned_at": "2026-08-27T11:10:52Z", "assigned_by": 1}	0	5	RESOLVED	2026-09-15 06:59:50.46311+00	2026-09-15 07:41:15.445091+00
110	ums_cdc.ums.user_role	0	74	USER_ROLE	user_id=5100027,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100027/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100027, "assigned_at": "2026-06-03T07:45:51Z", "assigned_by": 1}	0	5	RESOLVED	2026-09-15 06:59:50.821358+00	2026-09-15 07:41:17.026757+00
111	ums_cdc.ums.user_role	0	75	USER_ROLE	user_id=5100027,role_id=45	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100027/role_id=45 yet (user cached=False, role cached=True)	{"role_id": 45, "user_id": 5100027, "assigned_at": "2026-08-19T10:31:19Z", "assigned_by": 1}	0	5	RESOLVED	2026-09-15 06:59:51.143908+00	2026-09-15 07:41:18.328693+00
112	ums_cdc.ums.user_role	0	76	USER_ROLE	user_id=5100028,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100028/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100028, "assigned_at": "2026-06-16T13:32:30Z", "assigned_by": 5100022}	0	5	RESOLVED	2026-09-15 06:59:51.492338+00	2026-09-15 07:41:20.322454+00
113	ums_cdc.ums.user_role	0	77	USER_ROLE	user_id=5100029,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100029/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100029, "assigned_at": "2026-06-16T13:32:30Z", "assigned_by": 5100022}	0	5	RESOLVED	2026-09-15 06:59:51.908009+00	2026-09-15 07:41:21.723702+00
114	ums_cdc.ums.user_role	0	78	USER_ROLE	user_id=5100030,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100030/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100030, "assigned_at": "2026-06-16T13:32:30Z", "assigned_by": 5100022}	0	5	RESOLVED	2026-09-15 06:59:52.236544+00	2026-09-15 07:41:22.944125+00
115	ums_cdc.ums.user_role	0	79	USER_ROLE	user_id=5100031,role_id=3	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100031/role_id=3 yet (user cached=False, role cached=True)	{"role_id": 3, "user_id": 5100031, "assigned_at": "2026-09-10T14:27:56Z", "assigned_by": 5100009}	0	5	RESOLVED	2026-09-15 06:59:52.5366+00	2026-09-15 07:41:24.034642+00
116	ums_cdc.ums.user_role	0	80	USER_ROLE	user_id=5100031,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100031/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100031, "assigned_at": "2026-08-06T12:48:26Z", "assigned_by": 1}	0	5	RESOLVED	2026-09-15 06:59:52.88472+00	2026-09-15 07:41:25.196209+00
117	ums_cdc.ums.user_role	0	81	USER_ROLE	user_id=5100031,role_id=7	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100031/role_id=7 yet (user cached=False, role cached=True)	{"role_id": 7, "user_id": 5100031, "assigned_at": "2026-09-10T14:27:56Z", "assigned_by": 5100009}	0	5	RESOLVED	2026-09-15 06:59:53.213402+00	2026-09-15 07:41:26.776941+00
118	ums_cdc.ums.user_role	0	82	USER_ROLE	user_id=5100031,role_id=30	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100031/role_id=30 yet (user cached=False, role cached=True)	{"role_id": 30, "user_id": 5100031, "assigned_at": "2026-08-31T12:08:46Z", "assigned_by": 5100009}	0	5	RESOLVED	2026-09-15 06:59:53.506554+00	2026-09-15 07:41:27.789373+00
119	ums_cdc.ums.user_role	0	83	USER_ROLE	user_id=5100031,role_id=42	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100031/role_id=42 yet (user cached=False, role cached=True)	{"role_id": 42, "user_id": 5100031, "assigned_at": "2026-08-06T13:11:58Z", "assigned_by": 1}	0	5	RESOLVED	2026-09-15 06:59:53.824607+00	2026-09-15 07:41:28.756403+00
120	ums_cdc.ums.user_role	0	84	USER_ROLE	user_id=5100031,role_id=48	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100031/role_id=48 yet (user cached=False, role cached=True)	{"role_id": 48, "user_id": 5100031, "assigned_at": "2026-09-08T14:08:32Z", "assigned_by": 5100009}	0	5	RESOLVED	2026-09-15 06:59:54.119105+00	2026-09-15 07:41:29.828252+00
121	ums_cdc.ums.user_role	0	85	USER_ROLE	user_id=5100032,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100032/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100032, "assigned_at": "2026-09-03T07:24:22Z", "assigned_by": 5100013}	0	5	RESOLVED	2026-09-15 06:59:54.471678+00	2026-09-15 07:41:30.502563+00
122	ums_cdc.ums.user_role	0	86	USER_ROLE	user_id=5100033,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100033/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100033, "assigned_at": "2026-09-03T07:25:50Z", "assigned_by": 5100013}	0	5	RESOLVED	2026-09-15 06:59:54.755763+00	2026-09-15 07:41:31.349028+00
123	ums_cdc.ums.user_role	0	87	USER_ROLE	user_id=5100034,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100034/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100034, "assigned_at": "2026-09-03T09:15:13Z", "assigned_by": 5100013}	0	5	RESOLVED	2026-09-15 06:59:55.050944+00	2026-09-15 07:41:32.228926+00
124	ums_cdc.ums.user_role	0	88	USER_ROLE	user_id=5100035,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100035/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100035, "assigned_at": "2026-09-03T09:38:21Z", "assigned_by": 5100013}	0	5	RESOLVED	2026-09-15 06:59:55.340316+00	2026-09-15 07:41:33.48932+00
125	ums_cdc.ums.user_role	0	89	USER_ROLE	user_id=5100036,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100036/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100036, "assigned_at": "2026-09-04T06:37:46Z", "assigned_by": 5100013}	0	5	RESOLVED	2026-09-15 06:59:55.631358+00	2026-09-15 07:41:34.804629+00
126	ums_cdc.ums.user_role	0	90	USER_ROLE	user_id=5100037,role_id=4	r	MISSING_DEPENDENCY	Cannot resolve user_id=5100037/role_id=4 yet (user cached=False, role cached=True)	{"role_id": 4, "user_id": 5100037, "assigned_at": "2026-09-04T06:45:15Z", "assigned_by": 5100013}	0	5	RESOLVED	2026-09-15 06:59:55.948068+00	2026-09-15 07:41:36.273671+00
127	ums_cdc.ums.user	0	35	USER	019e8c6f-97b7-9061-d9d1-4704d264f454	u	MALFORMED_EVENT	Could not parse employee_uuid='5100020' as a UUID	{"mail": "aditya.bolli@pavestechnologies.com", "gender": "MALE", "contact": "+917815931935", "user_id": 5100020, "password": "$2b$12$cBmDqPHh3Z.EyNEEwvTKb.sgmJ/WV6UTvP2urHy77NaMwA5ivj/hK", "is_active": 1, "last_name": "Teja", "user_uuid": "019e8c6f-97b7-9061-d9d1-4704d264f454", "created_at": "2026-06-03T07:45:51Z", "first_name": "Bolli", "updated_at": "2026-09-15T06:59:34Z", "employee_id": "5100020", "last_login_at": 1789455574000, "last_login_ip": "52.46.56.79", "password_last_updated": 1780553635000}	0	5	RESOLVED	2026-09-15 06:59:56.317908+00	2026-09-15 07:41:38.440481+00
128	ums_cdc.ums.user	0	36	USER	019e68eb-06b3-ae1c-03d8-27e8949646eb	u	MALFORMED_EVENT	Could not parse employee_uuid='5100009' as a UUID	{"mail": "jagadish.pannala@pavestechnologies.com", "gender": "MALE", "contact": "+919100633230", "user_id": 5100009, "password": "$2b$12$2NYQSIbUNwto565lDHOpEuWt46imB9hpbeTjDoUs4EpTkVDmIydDi", "is_active": 1, "last_name": "Pannala", "user_uuid": "019e68eb-06b3-ae1c-03d8-27e8949646eb", "created_at": "2026-05-27T10:36:52Z", "first_name": "Jagadish", "updated_at": "2026-09-15T07:03:20Z", "employee_id": "5100009", "last_login_at": 1789455801000, "last_login_ip": "3.172.97.232", "password_last_updated": 1788259703000}	0	5	RESOLVED	2026-09-15 07:03:21.303689+00	2026-09-15 07:41:39.520146+00
129	ums_cdc.ums.user	0	37	USER	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	u	MALFORMED_EVENT	No synced EOS employee/department yet for employee_uuid=0199bd8c-ef11-0ff0-1695-f2d12b5bcea2 (user_id=1, user_uuid=0199bd8c-ef11-0ff0-1695-f2d12b5bcea2)	{"mail": "admin.paves@pavestechnologies.com", "gender": "MALE", "contact": "+919100633231", "user_id": 1, "password": "$2b$12$WbNhPsi0Xfdms8Q/Z63/KewnNbEK6C4p021YVu/xWSLPCJCGqT8M2", "is_active": 1, "last_name": "Admin", "user_uuid": "0199bd8c-ef11-0ff0-1695-f2d12b5bcea2", "created_at": "2025-10-07T01:52:34Z", "first_name": "Paves", "updated_at": "2026-09-15T07:05:38Z", "employee_id": "5100001", "last_login_at": 1789455939000, "last_login_ip": "52.46.56.79", "password_last_updated": 1761716755000}	0	5	RESOLVED	2026-09-15 07:05:39.210983+00	2026-09-15 10:48:06.172817+00
130	ums_cdc.ums.user	0	38	USER	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	u	MALFORMED_EVENT	No synced EOS employee/department yet for employee_uuid=0199bd8c-ef11-0ff0-1695-f2d12b5bcea2 (user_id=1, user_uuid=0199bd8c-ef11-0ff0-1695-f2d12b5bcea2)	{"mail": "admin.paves@pavestechnologies.com", "gender": "MALE", "contact": "+919100633231", "user_id": 1, "password": "$2b$12$WbNhPsi0Xfdms8Q/Z63/KewnNbEK6C4p021YVu/xWSLPCJCGqT8M2", "is_active": 1, "last_name": "Admin", "user_uuid": "0199bd8c-ef11-0ff0-1695-f2d12b5bcea2", "created_at": "2025-10-07T01:52:34Z", "first_name": "Paves", "updated_at": "2026-09-15T07:07:04Z", "employee_id": "5100001", "last_login_at": 1789456025000, "last_login_ip": "52.46.56.79", "password_last_updated": 1761716755000}	0	5	RESOLVED	2026-09-15 07:07:05.239674+00	2026-09-15 10:48:06.748906+00
131	ums_cdc.ums.user	0	39	USER	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	u	MALFORMED_EVENT	No synced EOS employee/department yet for employee_uuid=0199bd8c-ef11-0ff0-1695-f2d12b5bcea2 (user_id=1, user_uuid=0199bd8c-ef11-0ff0-1695-f2d12b5bcea2)	{"mail": "admin.paves@pavestechnologies.com", "gender": "MALE", "contact": "+919100633231", "user_id": 1, "password": "$2b$12$WbNhPsi0Xfdms8Q/Z63/KewnNbEK6C4p021YVu/xWSLPCJCGqT8M2", "is_active": 1, "last_name": "Admin", "user_uuid": "0199bd8c-ef11-0ff0-1695-f2d12b5bcea2", "created_at": "2025-10-07T01:52:34Z", "first_name": "Paves", "updated_at": "2026-09-15T07:10:39Z", "employee_id": "5100001", "last_login_at": 1789456239000, "last_login_ip": "52.46.56.79", "password_last_updated": 1761716755000}	0	5	RESOLVED	2026-09-15 07:10:39.664272+00	2026-09-15 10:48:07.141213+00
132	ums_cdc.ums.user_role	0	97	USER_ROLE	user_id=5100031,role_id=3	c	MISSING_DEPENDENCY	Cannot resolve user_id=5100031/role_id=3 yet (user cached=False, role cached=True)	{"role_id": 3, "user_id": 5100031, "assigned_at": "2026-09-15T07:13:37Z", "assigned_by": 5100009}	0	5	RESOLVED	2026-09-15 07:13:37.077317+00	2026-09-15 07:41:43.09035+00
133	ums_cdc.ums.user	0	40	USER	019e8c6f-97b7-9061-d9d1-4704d264f454	u	MALFORMED_EVENT	Could not parse employee_uuid='5100020' as a UUID	{"mail": "aditya.bolli@pavestechnologies.com", "gender": "MALE", "contact": "+917815931935", "user_id": 5100020, "password": "$2b$12$cBmDqPHh3Z.EyNEEwvTKb.sgmJ/WV6UTvP2urHy77NaMwA5ivj/hK", "is_active": 1, "last_name": "Teja", "user_uuid": "019e8c6f-97b7-9061-d9d1-4704d264f454", "created_at": "2026-06-03T07:45:51Z", "first_name": "Bolli", "updated_at": "2026-09-15T07:14:44Z", "employee_id": "5100020", "last_login_at": 1789456484000, "last_login_ip": "52.46.56.79", "password_last_updated": 1780553635000}	0	5	RESOLVED	2026-09-15 07:14:44.682523+00	2026-09-15 07:41:44.023148+00
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
1	IT	IT department	\N	t	2026-09-01 12:25:09.373161+00	2026-09-01 12:25:09.373161+00
2	HR	HR Adminstrators	\N	t	2026-09-01 12:44:03.704343+00	2026-09-01 12:44:03.704343+00
4	FIN	Finance	\N	t	2026-09-04 11:02:17.471654+00	2026-09-04 11:02:17.471654+00
5	ADMIN	Administration	\N	t	2026-09-04 11:02:38.888941+00	2026-09-04 11:02:38.888941+00
6	TEST_DEPT	for testing	\N	t	2026-09-07 06:27:02.881825+00	2026-09-07 06:27:02.881825+00
\.


--
-- Data for Name: department_approver; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.department_approver (id, department_id, user_uuid, is_active, created_at, updated_at, created_by) FROM stdin;
\.


--
-- Data for Name: department_purchase_category; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.department_purchase_category (department_id, purchase_category_id) FROM stdin;
\.


--
-- Data for Name: eos_department_cache; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.eos_department_cache (department_uuid, department_name, is_active, raw_payload, source_ts_ms, synced_at) FROM stdin;
54cf6e0c-1c42-40cf-8bc5-9d507724071e	Testing	t	{"created_at": 1780466674000, "updated_at": 1780466674000, "description": "", "department_id": 5, "department_name": "Testing", "department_uuid": "54cf6e0c-1c42-40cf-8bc5-9d507724071e"}	1789455354608	2026-09-15 06:59:14.757597+00
a36ca348-5992-11f1-bdde-027b59fbe807	Engineering	t	{"created_at": 1779862176000, "updated_at": 1779862176000, "description": "", "department_id": 1, "department_name": "Engineering", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807"}	1789455354607	2026-09-15 06:59:14.091886+00
a36ca9b4-5992-11f1-bdde-027b59fbe807	Human Resource	t	{"created_at": 1779862176000, "updated_at": 1779862176000, "description": "", "department_id": 2, "department_name": "Human Resource", "department_uuid": "a36ca9b4-5992-11f1-bdde-027b59fbe807"}	1789455354607	2026-09-15 06:59:14.266429+00
a36cab48-5992-11f1-bdde-027b59fbe807	Management	t	{"created_at": 1779862176000, "updated_at": 1779862176000, "description": "", "department_id": 3, "department_name": "Management", "department_uuid": "a36cab48-5992-11f1-bdde-027b59fbe807"}	1789455354608	2026-09-15 06:59:14.450057+00
a36cac52-5992-11f1-bdde-027b59fbe807	Devops	t	{"created_at": 1779862176000, "updated_at": 1779862176000, "description": "development and integration", "department_id": 4, "department_name": "Devops", "department_uuid": "a36cac52-5992-11f1-bdde-027b59fbe807"}	1789455354608	2026-09-15 06:59:14.604497+00
\.


--
-- Data for Name: eos_employee_cache; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.eos_employee_cache (employee_uuid, department_uuid, is_active, raw_payload, source_ts_ms, synced_at) FROM stdin;
019e68eb-06b3-ae1c-03d8-27e8949646eb	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 5, "gender": "Male", "location": "", "last_name": "Pannala", "user_uuid": "019e68eb-06b3-f390-42b6-851bb2d5f5b5", "work_mode": "Office", "bgv_status": "CLEARED", "created_at": 1779876694000, "created_by": "5100001", "first_name": "Jagadish", "updated_at": 1788330204000, "work_email": "jagadish.pannala@pavestechnologies.com", "bgv_remarks": "cleared", "blood_group": "O+", "employee_id": "5100009", "exported_at": "2026-06-03T06:23:59Z", "middle_name": "Reddy", "export_error": null, "joining_date": 20201, "date_of_birth": 11643, "employee_uuid": "019e68eb-06b3-ae1c-03d8-27e8949646eb", "export_status": "SUCCESS", "bgv_decided_by": "5100022", "contact_number": "+919100633230", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "AA==", "employment_status": "Probation", "reporting_manager_uuid": "5100023"}	1789455354503	2026-09-15 06:59:19.069015+00
019e6973-3a4d-65c2-0b0a-34f73c5f18ee	a36cab48-5992-11f1-bdde-027b59fbe807	t	{"id": 6, "gender": "Male", "location": "Hyderabad", "last_name": "Eada", "user_uuid": "019e6973-3a49-0fb8-c43b-58dcebd3ca36", "work_mode": "Remote", "bgv_status": "CLEARED", "created_at": 1779885620000, "created_by": "5100001", "first_name": "Sambi", "updated_at": 1781782080000, "work_email": "sambi.eada@pavestechnologies.com", "bgv_remarks": null, "blood_group": "A-", "employee_id": "5100025", "exported_at": "2026-06-03T06:23:59Z", "middle_name": "Reddy", "export_error": null, "joining_date": 20201, "date_of_birth": 3230, "employee_uuid": "019e6973-3a4d-65c2-0b0a-34f73c5f18ee", "export_status": "SUCCESS", "bgv_decided_by": "5100022", "contact_number": "4079699974", "marital_status": "Married", "department_uuid": "a36cab48-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83ecbd-5992-11f1-bdde-027b59fbe807", "total_experience": "ANw=", "employment_status": "Active", "reporting_manager_uuid": null}	1789455354506	2026-09-15 06:59:19.278939+00
019e8c25-0e73-7147-6bda-1279601ab9b4	a36cab48-5992-11f1-bdde-027b59fbe807	t	{"id": 7, "gender": "Male", "location": "Hyderabad", "last_name": "Durgam", "user_uuid": "019e8c25-0e73-3f01-f94a-e7238aa41cf4", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780467699000, "created_by": "5100001", "first_name": "Rama ", "updated_at": 1786015831000, "work_email": "ramagopal.durgam@pavestechnologies.com", "bgv_remarks": null, "blood_group": "B-", "employee_id": "5100023", "exported_at": "2026-06-03T06:23:59Z", "middle_name": "Gopal", "export_error": null, "joining_date": 20461, "date_of_birth": 2922, "employee_uuid": "019e8c25-0e73-7147-6bda-1279601ab9b4", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "8975645789", "marital_status": "Married", "department_uuid": "a36cab48-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f32f-5992-11f1-bdde-027b59fbe807", "total_experience": "AMg=", "employment_status": "Active", "reporting_manager_uuid": "5100025"}	1789455354507	2026-09-15 06:59:19.550504+00
019e8c42-2660-4fd6-56c8-14bc05878344	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 8, "gender": "Female", "location": "", "last_name": "Yanala", "user_uuid": "019e8c42-2660-29e4-72d4-5328cdcf2881", "work_mode": "Office", "bgv_status": "AWAITING_BGV_RESULT", "created_at": 1780469605000, "created_by": "5100001", "first_name": "Sindhu", "updated_at": 1788344532000, "work_email": "sindhu.yanala@pavestechnologies.com", "bgv_remarks": null, "blood_group": "A+", "employee_id": "5100014", "exported_at": null, "middle_name": "Reddy", "export_error": null, "joining_date": 20201, "date_of_birth": 12605, "employee_uuid": "019e8c42-2660-4fd6-56c8-14bc05878344", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "7396774639", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "AA==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354507	2026-09-15 06:59:19.83087+00
019e8c6f-9735-2eba-21f1-56f5d79c3256	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 9, "gender": "Male", "location": "Hyderabad", "last_name": "Saladi", "user_uuid": "019e8c6f-9735-ed90-0b73-828556448178", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472583000, "created_by": "5100001", "first_name": "Mohan Dharma Teja", "updated_at": 1783511600000, "work_email": "mohan.saladi@pavestechnologies.com", "bgv_remarks": null, "blood_group": "A+", "employee_id": "5100002", "exported_at": null, "middle_name": "Dharma Teja", "export_error": null, "joining_date": 20201, "date_of_birth": 12060, "employee_uuid": "019e8c6f-9735-2eba-21f1-56f5d79c3256", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "9704622099", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "AA==", "employment_status": "Probation", "reporting_manager_uuid": "5100023"}	1789455354508	2026-09-15 06:59:20.038582+00
019e8c6f-9746-823d-0fd1-572e7ff403c8	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 10, "gender": "Male", "location": "Hyderabad", "last_name": "Gajula", "user_uuid": "019e8c6f-9746-38fe-c6a6-4e37fc51ab2f", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Thejas", "updated_at": 1780473088000, "work_email": "thejas.gajula@pavestechnologies.com", "bgv_remarks": null, "blood_group": "A+", "employee_id": "5100003", "exported_at": null, "middle_name": null, "export_error": null, "joining_date": 20566, "date_of_birth": 12693, "employee_uuid": "019e8c6f-9746-823d-0fd1-572e7ff403c8", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "7330925101", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "Cg==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354508	2026-09-15 06:59:20.223722+00
019e8c6f-9754-6bc2-8378-21c15fe06b71	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 11, "gender": "Male", "location": "", "last_name": "Korada", "user_uuid": "019e8c6f-9754-3205-1365-c985a7fc4b4f", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Ajay", "updated_at": 1788326962000, "work_email": "ajay.korada@pavestechnologies.com", "bgv_remarks": null, "blood_group": "A-", "employee_id": "5100005", "exported_at": null, "middle_name": "Kumar", "export_error": null, "joining_date": 20202, "date_of_birth": 12185, "employee_uuid": "019e8c6f-9754-6bc2-8378-21c15fe06b71", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "7981773241", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "AA==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354508	2026-09-15 06:59:20.444971+00
019e8c6f-9763-00c7-b39c-59c56712443c	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 12, "gender": "Male", "location": "Hyderabad", "last_name": "alwala", "user_uuid": "019e8c6f-9763-3c63-2cdb-3ded809000be", "work_mode": "Hybrid", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "swarna", "updated_at": 1780912491000, "work_email": "swarnaraj.alwala@pavestechnologies.com", "bgv_remarks": null, "blood_group": "B+", "employee_id": "5100008", "exported_at": null, "middle_name": "raj ", "export_error": null, "joining_date": 20201, "date_of_birth": 12268, "employee_uuid": "019e8c6f-9763-00c7-b39c-59c56712443c", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "8096563083", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "Cg==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354509	2026-09-15 06:59:20.627852+00
019e8c6f-9772-c412-1177-4759698bb1d6	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 13, "gender": "Male", "location": "Hyderabad", "last_name": "Perka", "user_uuid": "019e8c6f-9772-8c15-3a55-924357d76bae", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Sathwik ", "updated_at": 1780473088000, "work_email": "sathwik.perka@pavestechnologies.com", "bgv_remarks": null, "blood_group": "B+", "employee_id": "5100010", "exported_at": null, "middle_name": null, "export_error": null, "joining_date": 20201, "date_of_birth": 12010, "employee_uuid": "019e8c6f-9772-c412-1177-4759698bb1d6", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "6309586236", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "Cg==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354511	2026-09-15 06:59:20.820589+00
019e8c6f-9781-e1a7-f161-74e0cfbca3cf	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 14, "gender": "Male", "location": "", "last_name": "Dama", "user_uuid": "019e8c6f-9781-4f1c-9fb6-4c7409914747", "work_mode": "Office", "bgv_status": "AWAITING_BGV_RESULT", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Rangaswamy", "updated_at": 1787033547000, "work_email": "rangaswamy.dama@pavestechnologies.com", "bgv_remarks": null, "blood_group": "A-", "employee_id": "5100012", "exported_at": null, "middle_name": "", "export_error": null, "joining_date": 20201, "date_of_birth": 12268, "employee_uuid": "019e8c6f-9781-e1a7-f161-74e0cfbca3cf", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "9059582200", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "Cg==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354512	2026-09-15 06:59:21.07133+00
019e8c6f-978f-f260-6d86-d768ec44ba6d	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 15, "gender": "Male", "location": "", "last_name": "Bhukya", "user_uuid": "019e8c6f-978f-2bad-d752-5c203847572a", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Ajay", "updated_at": 1785659461000, "work_email": "ajay.bhukya@pavestechnologies.com", "bgv_remarks": null, "blood_group": "O+", "employee_id": "5100013", "exported_at": null, "middle_name": "Kumar", "export_error": null, "joining_date": 20201, "date_of_birth": 12594, "employee_uuid": "019e8c6f-978f-f260-6d86-d768ec44ba6d", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "8688163153", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "AA==", "employment_status": "Probation", "reporting_manager_uuid": "5100023"}	1789455354513	2026-09-15 06:59:21.262556+00
019e8c6f-979e-7e3e-8fa3-74a2d4a9edb6	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 16, "gender": "Male", "location": "Hyderabad", "last_name": "lingarker", "user_uuid": "019e8c6f-979e-0233-d230-775fb6127769", "work_mode": "Office", "bgv_status": "AWAITING_BGV_RESULT", "created_at": 1780472584000, "created_by": "5100001", "first_name": "rohit", "updated_at": 1785409419000, "work_email": "rohit.lingarker@pavestechnologies.com", "bgv_remarks": null, "blood_group": "A+", "employee_id": "5100015", "exported_at": null, "middle_name": null, "export_error": null, "joining_date": 20201, "date_of_birth": 12300, "employee_uuid": "019e8c6f-979e-7e3e-8fa3-74a2d4a9edb6", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "7780294871", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "Cg==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354513	2026-09-15 06:59:21.445373+00
019e8c6f-97aa-842e-cde0-72514e55edda	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 17, "gender": "Female", "location": "Hyderabad", "last_name": "Balada", "user_uuid": "019e8c6f-97aa-9984-e3b0-c03db2d2e0db", "work_mode": "Office", "bgv_status": "AWAITING_BGV_RESULT", "created_at": 1780472584000, "created_by": "5100001", "first_name": "vijayadurga", "updated_at": 1785412803000, "work_email": "vijayadurga.balada@pavestechnologies.com", "bgv_remarks": null, "blood_group": "O+", "employee_id": "5100017", "exported_at": null, "middle_name": null, "export_error": null, "joining_date": 20201, "date_of_birth": 12049, "employee_uuid": "019e8c6f-97aa-842e-cde0-72514e55edda", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "7995041766", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "Cg==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354513	2026-09-15 06:59:21.636976+00
019e8c6f-97b7-9061-d9d1-4704d264f454	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 18, "gender": "Male", "location": "", "last_name": "Aditya Teja", "user_uuid": "019e8c6f-97b7-7efd-51ac-f48a25c68c39", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Bolli", "updated_at": 1781606034000, "work_email": "aditya.bolli@pavestechnologies.com", "bgv_remarks": null, "blood_group": "A+", "employee_id": "5100020", "exported_at": null, "middle_name": "Aditya", "export_error": null, "joining_date": 20124, "date_of_birth": 12435, "employee_uuid": "019e8c6f-97b7-9061-d9d1-4704d264f454", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "7815931935", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "AA==", "employment_status": "Probation", "reporting_manager_uuid": "5100023"}	1789455354514	2026-09-15 06:59:21.831711+00
019e8c6f-97c4-e62e-52b0-11b9e4816c88	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 19, "gender": "Female", "location": "Hyderabad", "last_name": "Niharika", "user_uuid": "019e8c6f-97c4-4a6b-4fab-3c280e6f9205", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Kandukoori", "updated_at": 1780473088000, "work_email": "niharika.kandukoori@pavestechnologies.com", "bgv_remarks": null, "blood_group": "A+", "employee_id": "5100021", "exported_at": null, "middle_name": null, "export_error": null, "joining_date": 20427, "date_of_birth": 12306, "employee_uuid": "019e8c6f-97c4-e62e-52b0-11b9e4816c88", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "9502528882", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "Cg==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354516	2026-09-15 06:59:22.043111+00
019e8c6f-97d0-6379-9078-0ba22e4ec921	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 20, "gender": "Male", "location": "Hyderabad", "last_name": "Gali", "user_uuid": "019e8c6f-97d0-ef08-9cdc-7cb00aae15bf", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Venkatesh", "updated_at": 1780473088000, "work_email": "venkatesh.gali@pavestechnologies.com", "bgv_remarks": null, "blood_group": "A+", "employee_id": "5100007", "exported_at": null, "middle_name": null, "export_error": null, "joining_date": 20201, "date_of_birth": 12391, "employee_uuid": "019e8c6f-97d0-6379-9078-0ba22e4ec921", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "9876534689", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "Cg==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354519	2026-09-15 06:59:22.298524+00
019e8c6f-97dc-c1a8-8790-1a2e9d1184a9	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 21, "gender": "Male", "location": "Hyderabad", "last_name": "Chilkuri", "user_uuid": "019e8c6f-97dc-110a-52b7-a9b10d69aebb", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Sri Charan", "updated_at": 1780482555000, "work_email": "sricharan.chilkuri@pavestechnologies.com", "bgv_remarks": null, "blood_group": "A+", "employee_id": "5100011", "exported_at": null, "middle_name": "Reddy", "export_error": null, "joining_date": 20201, "date_of_birth": 12106, "employee_uuid": "019e8c6f-97dc-c1a8-8790-1a2e9d1184a9", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "9346639366", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "Cg==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354519	2026-09-15 06:59:22.510865+00
019e8c6f-97e9-b9ea-8af9-06af6c630bea	a36ca9b4-5992-11f1-bdde-027b59fbe807	t	{"id": 22, "gender": "Female", "location": "", "last_name": "P", "user_uuid": "019e8c6f-97e9-5d1d-a202-2571c6d8f603", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Veni Priya ", "updated_at": 1788267397000, "work_email": "venipriya.p@pavestechnologies.com", "bgv_remarks": null, "blood_group": "B+", "employee_id": "5100022", "exported_at": null, "middle_name": null, "export_error": null, "joining_date": 20100, "date_of_birth": 10328, "employee_uuid": "019e8c6f-97e9-b9ea-8af9-06af6c630bea", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "6305877006", "marital_status": "Single", "department_uuid": "a36ca9b4-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f8fc-5992-11f1-bdde-027b59fbe807", "total_experience": "AA==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354520	2026-09-15 06:59:22.72961+00
019e8c6f-97f6-9cd6-2ecb-9bb7916d5ec4	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 23, "gender": "Female", "location": "hyderabad", "last_name": "U", "user_uuid": "019e8c6f-97f6-40d4-58b1-1bfbdf67d2e4", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Bindu Bhargavi", "updated_at": 1780473088000, "work_email": "bindub.usarti@pavestechnologies.com", "bgv_remarks": null, "blood_group": "O+", "employee_id": "5100026", "exported_at": null, "middle_name": null, "export_error": null, "joining_date": 20410, "date_of_birth": 11892, "employee_uuid": "019e8c6f-97f6-9cd6-2ecb-9bb7916d5ec4", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "8328561719", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83fc32-5992-11f1-bdde-027b59fbe807", "total_experience": "PA==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354520	2026-09-15 06:59:22.926339+00
019e8c6f-9805-1c42-431e-15c89a2f1ad8	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 24, "gender": "Male", "location": "hyderabad", "last_name": "P", "user_uuid": "019e8c6f-9805-901b-858d-bdb95aac3130", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Kalasagar", "updated_at": 1780473088000, "work_email": "kalasagar.p@pavestechnologies.com", "bgv_remarks": null, "blood_group": "O+", "employee_id": "5100027", "exported_at": null, "middle_name": null, "export_error": null, "joining_date": 20096, "date_of_birth": 11298, "employee_uuid": "019e8c6f-9805-1c42-431e-15c89a2f1ad8", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "9381951224", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83fc32-5992-11f1-bdde-027b59fbe807", "total_experience": "ZA==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354520	2026-09-15 06:59:23.204328+00
019e8c6f-9812-9a50-5d66-fa4dca42de44	a36ca9b4-5992-11f1-bdde-027b59fbe807	t	{"id": 25, "gender": "Male", "location": "hyderabad", "last_name": "K", "user_uuid": "019e8c6f-9812-7402-6f28-35ed1f06cafb", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1780472584000, "created_by": "5100001", "first_name": "Rakesh", "updated_at": 1780473088000, "work_email": "Rakesh.K@pavestechnologies.com", "bgv_remarks": null, "blood_group": "B+", "employee_id": "5100024", "exported_at": null, "middle_name": null, "export_error": null, "joining_date": 20486, "date_of_birth": 11234, "employee_uuid": "019e8c6f-9812-9a50-5d66-fa4dca42de44", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "6303423477", "marital_status": "Single", "department_uuid": "a36ca9b4-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83fac9-5992-11f1-bdde-027b59fbe807", "total_experience": "LA==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354521	2026-09-15 06:59:23.456365+00
3e89bf42-0dda-4fc1-b67e-8590c0f444ad	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 27, "gender": "Female", "location": "Hyderabad", "last_name": "pathan", "user_uuid": "019e9728-d417-2d7b-b55a-3121bc2fb262", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1781614506000, "created_by": "5100022", "first_name": "sumiya", "updated_at": 1783681264000, "work_email": "sumiya.patha@pavestechnologies.com", "bgv_remarks": null, "blood_group": "O+", "employee_id": "5100029", "exported_at": "2026-06-16T13:32:42Z", "middle_name": "khanam", "export_error": null, "joining_date": 20621, "date_of_birth": 12576, "employee_uuid": "3e89bf42-0dda-4fc1-b67e-8590c0f444ad", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "6302883868", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "Cg==", "employment_status": "Active", "reporting_manager_uuid": "5100023"}	1789455354526	2026-09-15 06:59:23.858985+00
a858c3ff-9b6c-412f-8c64-b6803f817d9a	a36ca348-5992-11f1-bdde-027b59fbe807	t	{"id": 26, "gender": "Male", "location": "Hyderabad", "last_name": "user", "user_uuid": "019ed040-3918-14c3-6485-592dc5e73310", "work_mode": "Office", "bgv_status": "NOT_STARTED", "created_at": 1781613594000, "created_by": "5100022", "first_name": "Test", "updated_at": 1781616762000, "work_email": "test.user@pavestechnologies.com", "bgv_remarks": null, "blood_group": "A+", "employee_id": "5100028", "exported_at": "2026-06-16T13:32:42Z", "middle_name": "", "export_error": null, "joining_date": 20621, "date_of_birth": 12576, "employee_uuid": "a858c3ff-9b6c-412f-8c64-b6803f817d9a", "export_status": "SUCCESS", "bgv_decided_by": null, "contact_number": "7396777850", "marital_status": "Single", "department_uuid": "a36ca348-5992-11f1-bdde-027b59fbe807", "employment_type": "Full-Time", "designation_uuid": "de83f5b6-5992-11f1-bdde-027b59fbe807", "total_experience": "Cg==", "employment_status": "Probation", "reporting_manager_uuid": "5100023"}	1789455354525	2026-09-15 06:59:23.647673+00
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
122	UPLOAD	\N	\N	\N	2026-09-23 12:21:09.664274	aws-gst-invoice-may-2026.pdf	invoices/2026/09/8175a1d73dfc4509be002c759de162eb_aws-gst-invoice-may-2026.pdf	EXTRACTED	91.96	{"tax": {"hsn_sac": "998315", "tax_type": "INTER_STATE_IGST", "cess_rate": null, "cgst_rate": null, "igst_rate": 18.0, "sgst_rate": null, "ugst_rate": null, "reverse_charge": false, "place_of_supply": "Telangana"}, "buyer": {"pan": null, "name": "Paves Global Infotech pvt ltd", "email": null, "gstin": null, "phone": null, "state": null, "address": "Paves Global Infotech pvt ltd\\nGachibowli\\nGachibowli\\nHyderabad, Telangana, 500032, IN", "country": null, "legal_name": "Paves Global Infotech pvt ltd", "state_code": null, "trade_name": null, "shipping_address": null}, "vendor": {"pan": "AAJCA9880A", "name": "Amazon Web Services India Private Limited", "email": null, "gstin": "07AAJCA9880A1ZL", "phone": null, "state": "Delhi", "address": "Amazon Web Services India Private Limited\\n(formerly known as Amazon Internet Services Private Limited)\\nBlock E, 14th Floor, Unit Nos. 1401 to 1421 International Trade Tower, Nehru Place,\\nNew Delhi, Delhi, 110019", "country": null, "website": null, "legal_name": "Amazon Web Services India Private Limited", "state_code": "07", "trade_name": null}, "amounts": {"discount": 8875.55, "subtotal": 3055.72, "round_off": null, "total_tax": 550.03, "tds_amount": null, "amount_paid": null, "balance_due": null, "cess_amount": null, "cgst_amount": null, "grand_total": 3605.75, "igst_amount": 550.03, "sgst_amount": null, "ugst_amount": null, "other_charges": null, "taxable_amount": null, "freight_charges": null, "handling_charges": null, "shipping_charges": null}, "payment": {"branch": null, "upi_id": null, "bank_name": null, "ifsc_code": null, "swift_code": null, "account_name": null, "payment_terms": null, "account_number": "743737183908"}, "document": {"currency": "INR", "due_date": "2026-06-02", "invoice_date": "2026-06-01", "invoice_type": "TAX_INVOICE", "document_type": "invoice", "invoice_number": "AIN2627000969471", "original_filename": "aws-gst-invoice-may-2026.pdf"}, "reference": {"po_date": null, "po_number": "", "order_number": null, "quotation_date": null, "contract_number": null, "quotation_number": null, "reference_number": null, "delivery_note_date": null, "delivery_note_number": null}, "compliance": {"irn": null, "qr_code_data": null, "export_invoice": null, "reverse_charge": false, "einvoice_status": null, "acknowledgement_date": null, "acknowledgement_number": null}, "extraction": {"job_id": "fbdc198683d8816c7fa78df0e2ed7a24934ae8192287b3d92dbff01cb915ac6a", "status": "SUCCESS", "provider": "AWS_TEXTRACT", "warnings": [], "confidence": 91.964919090271, "field_details": {"hsn_sac": {"page": null, "value": "998315", "source": "REGEX_FULLTEXT", "confidence": 75, "bounding_box": null, "extraction_method": "REGEX"}, "discount": {"page": 1, "value": "Rs. 8,875.55", "source": "TEXTRACT_SUMMARY", "confidence": 90.01663970947266, "bounding_box": {"top": 0.6363275051116943, "left": 0.8528769612312317, "page": 1, "width": 0.0817210003733635, "height": 0.010939175263047218}, "extraction_method": "TEXTRACT_SUMMARY"}, "subtotal": {"page": 1, "value": "Rs. 3,055.72", "source": "TEXTRACT_SUMMARY", "confidence": 98.76010131835938, "bounding_box": {"top": 0.661628782749176, "left": 0.8506456613540649, "page": 1, "width": 0.08421733230352402, "height": 0.010877221822738647}, "extraction_method": "TEXTRACT_SUMMARY"}, "tax_type": {"page": null, "value": "INTER_STATE_IGST", "source": "DERIVED", "confidence": null, "bounding_box": null, "extraction_method": "DERIVED"}, "igst_rate": {"page": null, "value": 18, "source": "REGEX_FULLTEXT", "confidence": 75, "bounding_box": null, "extraction_method": "REGEX"}, "total_tax": {"page": 1, "value": "Rs. 550.03", "source": "TEXTRACT_SUMMARY", "confidence": 92.52362823486328, "bounding_box": {"top": 0.2706327438354492, "left": 0.8550602197647095, "page": 1, "width": 0.07703360915184021, "height": 0.010808242484927177}, "extraction_method": "TEXTRACT_SUMMARY"}, "buyer_name": {"page": 1, "value": "Paves Global Infotech pvt ltd", "source": "TEXTRACT_SUMMARY", "confidence": 99.868896484375, "bounding_box": {"top": 0.27347344160079956, "left": 0.058535024523735046, "page": 1, "width": 0.2137630432844162, "height": 0.01320679672062397}, "extraction_method": "TEXTRACT_SUMMARY"}, "vendor_pan": {"page": null, "value": "AAJCA9880A", "source": "DERIVED_FROM_GSTIN", "confidence": 85, "bounding_box": null, "extraction_method": "DERIVED"}, "grand_total": {"page": 1, "value": "Rs. 3,605.75", "source": "TEXTRACT_SUMMARY", "confidence": 97.93067932128906, "bounding_box": {"top": 0.23132722079753876, "left": 0.841490626335144, "page": 1, "width": 0.09071436524391174, "height": 0.01200246624648571}, "extraction_method": "TEXTRACT_SUMMARY"}, "igst_amount": {"page": null, "value": 550.03, "source": "REGEX_FULLTEXT", "confidence": 75, "bounding_box": null, "extraction_method": "REGEX"}, "vendor_name": {"page": 1, "value": "Amazon Web Services India Private Limited", "source": "TEXTRACT_SUMMARY", "confidence": 99.90094757080078, "bounding_box": {"top": 0.8702061176300049, "left": 0.3877818286418915, "page": 1, "width": 0.22275735437870026, "height": 0.008322509005665779}, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_date": {"page": 1, "value": "2026.06.01", "source": "TEXTRACT_SUMMARY", "confidence": 92.73100280761719, "bounding_box": {"top": 0.038777146488428116, "left": 0.08736664056777954, "page": 1, "width": 0.05068449303507805, "height": 0.0067760758101940155}, "extraction_method": "TEXTRACT_SUMMARY"}, "invoice_type": {"page": null, "value": "TAX_INVOICE", "source": "REGEX_FULLTEXT", "confidence": 80, "bounding_box": null, "extraction_method": "REGEX"}, "vendor_gstin": {"page": null, "value": "07AAJCA9880A1ZL", "source": "REGEX_FULLTEXT_ANCHORED", "confidence": 85, "bounding_box": null, "extraction_method": "REGEX"}, "buyer_address": {"page": 1, "value": "Paves Global Infotech pvt ltd\\nGachibowli\\nGachibowli\\nHyderabad, Telangana, 500032, IN", "source": "TEXTRACT_SUMMARY", "confidence": 99.31129455566406, "bounding_box": {"top": 0.27345049381256104, "left": 0.0579727441072464, "page": 1, "width": 0.25574803352355957, "height": 0.05883476510643959}, "extraction_method": "TEXTRACT_SUMMARY"}, "account_number": {"page": 1, "value": "743737183908", "source": "TEXTRACT_SUMMARY", "confidence": 99.9194107055664, "bounding_box": {"top": 0.18321198225021362, "left": 0.05810021981596947, "page": 1, "width": 0.17176002264022827, "height": 0.01529687363654375}, "extraction_method": "TEXTRACT_SUMMARY"}, "billing_period": {"page": 1, "value": "May 1 - May 31, 2026", "source": "TEXTRACT_QUERY", "confidence": 92, "bounding_box": {"top": 0.4608170688152313, "left": 0.47647523880004883, "page": 1, "width": 0.22183974087238312, "height": 0.017339976504445076}, "extraction_method": "TEXTRACT_QUERY"}, "invoice_number": {"page": 1, "value": "AIN2627000969471", "source": "TEXTRACT_SUMMARY", "confidence": 98.3331298828125, "bounding_box": {"top": 0.18843643367290497, "left": 0.7802793383598328, "page": 1, "width": 0.14997155964374542, "height": 0.010707736946642399}, "extraction_method": "TEXTRACT_SUMMARY"}, "reverse_charge": {"page": 1, "value": false, "source": "TEXTRACT_QUERY", "confidence": 61, "bounding_box": null, "extraction_method": "TEXTRACT_QUERY"}, "vendor_address": {"page": 1, "value": "Amazon Web Services India Private Limited\\n(formerly known as Amazon Internet Services Private Limited)\\nBlock E, 14th Floor, Unit Nos. 1401 to 1421 International Trade Tower, Nehru Place,\\nNew Delhi, Delhi, 110019", "source": "TEXTRACT_SUMMARY", "confidence": 99.02031707763672, "bounding_box": {"top": 0.8702850937843323, "left": 0.2871413230895996, "page": 1, "width": 0.4234562814235687, "height": 0.04193377122282982}, "extraction_method": "TEXTRACT_SUMMARY"}, "place_of_supply": {"page": 1, "value": "Telangana", "source": "TEXTRACT_QUERY", "confidence": 99, "bounding_box": {"top": 0.3577846586704254, "left": 0.058262936770915985, "page": 1, "width": 0.07639160007238388, "height": 0.01300467737019062}, "extraction_method": "TEXTRACT_QUERY"}, "buyer_legal_name": {"page": 1, "value": "Paves Global Infotech pvt ltd", "source": "DERIVED_FROM_NAME", "confidence": 99.868896484375, "bounding_box": null, "extraction_method": "DERIVED"}, "vendor_legal_name": {"page": 1, "value": "Amazon Web Services India Private Limited", "source": "DERIVED_FROM_NAME", "confidence": 99.90094757080078, "bounding_box": null, "extraction_method": "DERIVED"}}, "field_sources": {"hsn_sac": "REGEX_FULLTEXT", "discount": "TEXTRACT_SUMMARY", "subtotal": "TEXTRACT_SUMMARY", "igst_rate": "REGEX_FULLTEXT", "total_tax": "TEXTRACT_SUMMARY", "buyer_name": "TEXTRACT_SUMMARY", "vendor_pan": "DERIVED_FROM_GSTIN", "grand_total": "TEXTRACT_SUMMARY", "igst_amount": "REGEX_FULLTEXT", "vendor_name": "TEXTRACT_SUMMARY", "invoice_date": "TEXTRACT_SUMMARY", "invoice_type": "REGEX_FULLTEXT", "vendor_gstin": "REGEX_FULLTEXT_ANCHORED", "buyer_address": "TEXTRACT_SUMMARY", "account_number": "TEXTRACT_SUMMARY", "billing_period": "TEXTRACT_QUERY", "invoice_number": "TEXTRACT_SUMMARY", "reverse_charge": "TEXTRACT_QUERY", "vendor_address": "TEXTRACT_SUMMARY", "place_of_supply": "TEXTRACT_QUERY", "buyer_legal_name": "DERIVED_FROM_NAME", "vendor_legal_name": "DERIVED_FROM_NAME"}, "pages_processed": 3, "field_confidence": {"hsn_sac": 75.0, "discount": 90.01663970947266, "subtotal": 98.76010131835938, "igst_rate": 75.0, "total_tax": 92.52362823486328, "buyer_name": 99.868896484375, "vendor_pan": 85.0, "grand_total": 97.93067932128906, "igst_amount": 75.0, "vendor_name": 99.90094757080078, "invoice_date": 92.73100280761719, "invoice_type": 80.0, "vendor_gstin": 85.0, "buyer_address": 99.31129455566406, "account_number": 99.9194107055664, "billing_period": 92.0, "invoice_number": 98.3331298828125, "reverse_charge": 61.0, "vendor_address": 99.02031707763672, "place_of_supply": 99.0, "buyer_legal_name": 99.868896484375, "vendor_legal_name": 99.90094757080078}}, "raw_fields": {"query_results": {"BILLING_PERIOD": {"page": 1, "value": "May 1 - May 31, 2026", "confidence": 92, "bounding_box": {"top": 0.4608170688152313, "left": 0.47647523880004883, "page": 1, "width": 0.22183974087238312, "height": 0.017339976504445076}}, "REVERSE_CHARGE": {"page": 1, "value": "No", "confidence": 61, "bounding_box": null}, "PLACE_OF_SUPPLY": {"page": 1, "value": "Telangana", "confidence": 99, "bounding_box": {"top": 0.3577846586704254, "left": 0.058262936770915985, "page": 1, "width": 0.07639160007238388, "height": 0.01300467737019062}}}}, "validation": {"issues": [], "status": "READY_FOR_VALIDATION", "is_valid": true, "warnings": ["Buyer GSTIN could not be confidently extracted."], "field_issues": [{"code": "MISSING_FIELD", "field": "buyer_gstin", "message": "Buyer GSTIN could not be confidently extracted."}], "tax_difference": 0.0, "total_difference": 0.0}, "invoice_lines": [{"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 3605.75, "unit_price": 3605.75, "cess_amount": null, "cgst_amount": null, "description": null, "igst_amount": null, "line_number": 1, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 0.0, "unit_price": 0.0, "cess_amount": null, "cgst_amount": null, "description": "Credits/Discount", "igst_amount": null, "line_number": 2, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 503.26, "unit_price": 503.26, "cess_amount": null, "cgst_amount": null, "description": "Amazon Relational Database Service", "igst_amount": null, "line_number": 3, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 19.05, "unit_price": 19.05, "cess_amount": null, "cgst_amount": null, "description": "AWS Systems Manager", "igst_amount": null, "line_number": 4, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 314.96, "unit_price": 314.96, "cess_amount": null, "cgst_amount": null, "description": "AWS Secrets Manager", "igst_amount": null, "line_number": 5, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 0.0, "unit_price": 0.0, "cess_amount": null, "cgst_amount": null, "description": "Amazon Elastic Compute Cloud", "igst_amount": null, "line_number": 6, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 11.21, "unit_price": 11.21, "cess_amount": null, "cgst_amount": null, "description": "Amazon EC2 Container Registry (ECR)", "igst_amount": null, "line_number": 7, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 112.08, "unit_price": 112.08, "cess_amount": null, "cgst_amount": null, "description": "AWS Key Management Service", "igst_amount": null, "line_number": 8, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}, {"unit": null, "hsn_sac": null, "discount": null, "quantity": null, "tax_rate": null, "cess_rate": null, "cgst_rate": null, "igst_rate": null, "sgst_rate": null, "total_tax": null, "ugst_rate": null, "line_total": 2644.07, "unit_price": 2644.07, "cess_amount": null, "cgst_amount": null, "description": "Amazon Virtual Private Cloud", "igst_amount": null, "line_number": 9, "sgst_amount": null, "ugst_amount": null, "product_code": null, "taxable_amount": null}]}	15	99	2026-09-23 12:21:09.664274
\.


--
-- Data for Name: invoice; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice (invoice_id, invoice_number, vendor_id, inbound_document_id, invoice_type, po_id, grn_id, invoice_date, due_date, payment_term_id, currency_id, gross_amount, discount_amount, tax_amount, net_amount, amount_paid, status_id, created_by, created_at, updated_by, updated_at, department_id, purchase_category_id) FROM stdin;
99	AIN2627000969471	15	122	NON_PO	\N	\N	2026-06-01	2026-06-02	\N	1	3605.75	8875.55	550.03	3605.75	0.00	41	5100007	2026-09-23 12:21:09.664274	5100007	2026-09-23 12:21:09.664274	1	2
\.


--
-- Data for Name: invoice_approval; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice_approval (invoice_approval_id, invoice_id, approval_policy_id, status, created_at, invoice_issue_id, completed_at) FROM stdin;
\.


--
-- Data for Name: invoice_approval_legacy; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice_approval_legacy (invoice_approval_id, invoice_id, invoice_issue_id, approver_name, decision, comments, decided_at, created_at) FROM stdin;
\.


--
-- Data for Name: invoice_approval_step; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice_approval_step (id, invoice_approval_id, level_number, approver_type, approval_rule, status, created_at, updated_at, role_code, department_id, started_at, completed_at) FROM stdin;
\.


--
-- Data for Name: invoice_approval_step_approver; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice_approval_step_approver (id, approval_step_id, user_uuid, status, created_at, updated_at, decided_at, comments) FROM stdin;
\.


--
-- Data for Name: invoice_attachment; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice_attachment (invoice_attachment_id, invoice_id, file_name, file_path, uploaded_at) FROM stdin;
94	99	aws-gst-invoice-may-2026.pdf	invoices/2026/09/8175a1d73dfc4509be002c759de162eb_aws-gst-invoice-may-2026.pdf	2026-09-23 12:21:09.664274
\.


--
-- Data for Name: invoice_issue; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice_issue (invoice_issue_id, invoice_id, issue_source, issue_type, severity, result, description, status_id, resolved_by, resolved_at, created_at) FROM stdin;
\.


--
-- Data for Name: invoice_line; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice_line (invoice_line_id, invoice_id, line_number, description, quantity, unit_price, line_amount, tax_type_id, tax_amount, po_line_id) FROM stdin;
209	99	1		1.0000	3605.7500	3605.75	\N	0.00	\N
210	99	2	Credits/Discount	1.0000	0.0000	0.00	\N	0.00	\N
211	99	3	Amazon Relational Database Service	1.0000	503.2600	503.26	\N	0.00	\N
212	99	4	AWS Systems Manager	1.0000	19.0500	19.05	\N	0.00	\N
213	99	5	AWS Secrets Manager	1.0000	314.9600	314.96	\N	0.00	\N
214	99	6	Amazon Elastic Compute Cloud	1.0000	0.0000	0.00	\N	0.00	\N
215	99	7	Amazon EC2 Container Registry (ECR)	1.0000	11.2100	11.21	\N	0.00	\N
216	99	8	AWS Key Management Service	1.0000	112.0800	112.08	\N	0.00	\N
217	99	9	Amazon Virtual Private Cloud	1.0000	2644.0700	2644.07	\N	0.00	\N
\.


--
-- Data for Name: invoice_tds; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.invoice_tds (id, invoice_id, tds_applicable, payment_nature_id, tds_rule_id, tds_rate_rule_id, taxable_base, tds_rate, tds_amount, threshold_amount, prior_period_aggregate, current_transaction_amount, aggregate_amount, pan_status, entity_type, determination_status, determination_reason, determined_at, determined_by, verified_at, verified_by, remarks, created_at, updated_at, gstin_status, gstin_checked_at) FROM stdin;
\.


--
-- Data for Name: nda_template; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.nda_template (id, code, name, version, body, is_active, created_at, updated_at, created_by, updated_by) FROM stdin;
1	STANDARD_NDA	Standard Non-Disclosure Agreement	1.0	\nNON-DISCLOSURE AGREEMENT\n\nThis Non-Disclosure Agreement ("Agreement") is entered into on {{NDA_DATE}}.\n\nBETWEEN\n\n{{COMPANY_NAME}}\n{{COMPANY_ADDRESS}}\n\nAND\n\n{{VENDOR_NAME}}\nVendor Code: {{VENDOR_CODE}}\n{{VENDOR_ADDRESS}}\n\nVendor Email: {{VENDOR_EMAIL}}\nPAN: {{VENDOR_PAN}}\nGSTIN: {{VENDOR_GSTIN}}\n\n1. PURPOSE\n\nThis Agreement is entered into in connection with:\n\nPR Number: {{PR_NUMBER}}\nPR Date: {{PR_DATE}}\nDepartment: {{DEPARTMENT}}\nPurchase Category: {{PURCHASE_CATEGORY}}\n\nBusiness Requirement:\n{{BUSINESS_REQUIREMENT}}\n\n2. CONFIDENTIAL INFORMATION\n\nThe parties agree to maintain the confidentiality of all confidential,\ntechnical, commercial, financial, operational and business information\nshared in connection with the above business requirement.\n\n3. USE OF CONFIDENTIAL INFORMATION\n\nThe receiving party shall use confidential information only for the\npurpose for which it has been disclosed and shall not disclose such\ninformation to unauthorized third parties.\n\n4. CONFIDENTIALITY OBLIGATIONS\n\nThe receiving party shall take reasonable measures to protect confidential\ninformation from unauthorized access, disclosure, copying or use.\n\n5. TERM\n\nThis Agreement shall remain effective according to the applicable\ncontractual terms agreed between the parties.\n\n6. SIGNATORIES\n\nFor {{COMPANY_NAME}}\n\nName: {{COMPANY_SIGNATORY}}\n\nSignature: ______________________\n\nDate: {{NDA_DATE}}\n\n\nFor {{VENDOR_NAME}}\n\nAuthorized Signatory: ______________________\n\nSignature: ______________________\n\nDate: ______________________\n	t	2026-09-21 10:33:10.20858	2026-09-21 10:33:10.20858	system	system
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

COPY ap.purchase_category (id, code, name, description, is_active, created_at, updated_at, department_id) FROM stdin;
1	IT_HARDWARE	IT hardware	\N	t	2026-09-01 13:29:39.529139+00	2026-09-01 13:29:39.529139+00	1
2	IT_SOFTWARE	IT software	\N	t	2026-09-01 13:30:10.638187+00	2026-09-01 13:30:10.638187+00	1
3	FIN_AUDIT	Audit Services	\N	t	2026-09-04 11:04:41.477892+00	2026-09-04 11:04:41.477892+00	4
4	FIN_ACCOUNTING	Accounting Services	\N	t	2026-09-04 11:05:04.393556+00	2026-09-04 11:05:04.393556+00	4
5	ADMIN_OFFICE	Office Supplies	\N	t	2026-09-04 11:05:33.396573+00	2026-09-04 11:05:33.396573+00	5
6	ADMIN_FACILITIES	Facilities & Maintenance	\N	t	2026-09-04 11:05:53.484135+00	2026-09-04 11:05:53.484135+00	5
7	TEST_CAT_ONE	test category one	\N	t	2026-09-07 06:27:40.300626+00	2026-09-07 06:27:40.300626+00	6
\.


--
-- Data for Name: purchase_category_tds_mapping; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.purchase_category_tds_mapping (id, purchase_category_id, tds_payment_nature_id, is_default, is_active, created_at, updated_at) FROM stdin;
1	1	6	t	t	2026-09-23 07:05:17.343556	2026-09-23 07:05:17.343556
2	2	2	t	t	2026-09-23 07:05:17.343556	2026-09-25 05:04:19.742322
3	4	8	t	t	2026-09-23 07:05:17.343556	2026-09-23 07:05:17.343556
4	3	8	t	t	2026-09-23 07:05:17.343556	2026-09-23 07:05:17.343556
5	6	8	t	t	2026-09-23 07:05:17.343556	2026-09-23 07:05:17.343556
6	5	6	t	t	2026-09-23 07:05:17.343556	2026-09-25 05:04:19.847974
7	7	8	t	t	2026-09-23 07:05:17.343556	2026-09-23 07:05:17.343556
\.


--
-- Data for Name: purchase_order; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.purchase_order (id, po_number, pr_id, quotation_id, vendor_id, po_date, expected_delivery_date, delivery_location, payment_terms, delivery_terms, subtotal, tax_amount, total_amount, status_id, created_by, created_at, updated_at) FROM stdin;
3	PO-000003	3	3	15	2026-09-02	\N	\N	\N	\N	500000.00	0.00	500000.00	14	1	2026-09-02 12:12:42.937067+00	2026-09-02 12:12:42.937067+00
\.


--
-- Data for Name: purchase_order_line; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.purchase_order_line (id, po_id, pr_line_id, item_name, description, quantity, uom, unit_price, tax_rate, tax_amount, total_amount, created_at, updated_at) FROM stdin;
3	3	3	DELL	\N	10.0000	EA	50000.00	0.0000	0.00	500000.00	2026-09-02 12:12:42.937067+00	2026-09-02 12:12:42.937067+00
\.


--
-- Data for Name: purchase_requisition; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.purchase_requisition (id, pr_number, department_id, purchase_category_id, status_id, priority, required_by, delivery_location, justification, estimated_total, selected_vendor_id, selected_quotation_id, approved_by, approved_at, approval_comment, created_by, created_at, updated_at, sourcing_type, selection_reason) FROM stdin;
3	PR-000003	1	1	28	NORMAL	2026-09-20	Hyderabad	new employees onboarded , we need 10 laptops requirements	500000.00	15	3	1	2026-09-02 11:55:55.235484+00	\N	1	2026-09-02 11:06:24.759393+00	2026-09-02 11:06:24.759393+00	\N	\N
\.


--
-- Data for Name: purchase_requisition_line; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.purchase_requisition_line (id, pr_id, item_name, description, quantity, uom, estimated_unit_price, estimated_amount, created_at, updated_at, is_custom_uom) FROM stdin;
3	3	DELL	\N	10.0000	EA	50000.00	500000.00	2026-09-02 11:51:00.41017+00	2026-09-02 11:51:00.41017+00	f
\.


--
-- Data for Name: quotation; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.quotation (id, quotation_number, pr_id, vendor_id, quotation_date, valid_until, total_amount, file_url, status_id, created_by, created_at, updated_at, rfq_id, delivery_days, payment_terms) FROM stdin;
3	QT-2026-0142	3	15	2026-09-02	2026-09-30	436600.00	invoices/2026/09/09ae41dabd6343449b9302a3325c44b3_sample_vendor_quotation_QT-2026-0142.pdf	32	1	2026-09-02 12:10:12.435286+00	2026-09-02 12:10:12.435286+00	\N	\N	\N
\.


--
-- Data for Name: rfq; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.rfq (id, rfq_number, pr_id, status_id, created_by, created_at, updated_at, due_date, sent_at, closed_by, closed_at) FROM stdin;
\.


--
-- Data for Name: rfq_vendor; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.rfq_vendor (id, rfq_id, vendor_id, invited_by, invited_at) FROM stdin;
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
8	INVOICE	PENDING_APPROVAL	Pending Approval	5
9	INVOICE	APPROVED	Approved	6
10	INVOICE	REJECTED	Rejected	7
11	INVOICE	PARTIALLY_PAID	Partially Paid	10
12	INVOICE	PAID	Paid	11
13	INVOICE	DISPUTED	Disputed	12
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
34	RFQ	DRAFT	Draft	10
35	RFQ	SENT	Sent	20
36	RFQ	RESPONSE_RECEIVED	Response Received	30
37	RFQ	CLOSED	Closed	40
38	PURCHASE_REQUISITION	RETURNED	Returned for Clarification	25
39	INVOICE	READY_FOR_PAYMENT	Ready for Payment	9
40	INVOICE	RETURNED_FOR_REVIEW	Returned for Review	8
41	INVOICE	OCR_REVIEWED	OCR Reviewed	4
42	VENDOR_ONBOARDING	CREATED	Created	1
43	VENDOR_ONBOARDING	ASSIGNED	Assigned	2
44	VENDOR_ONBOARDING	IN_PROGRESS	In Progress	3
45	VENDOR_ONBOARDING	PRE_SCREENING	Pre-Screening	4
46	VENDOR_ONBOARDING	NDA_PENDING	NDA Pending	5
47	VENDOR_ONBOARDING	COMPLETED	Completed	6
48	VENDOR_ONBOARDING	FAILED	Failed	7
49	VENDOR_ONBOARDING	CANCELLED	Cancelled	8
50	VENDOR_ONBOARDING	PRE_SCREEN_PENDING	Pre-Screen Pending	4
51	VENDOR_ONBOARDING	PASSED	Passed	9
84	NDA	NOT_REQUIRED	Not Required	1
85	NDA	PENDING	Pending	2
86	NDA	SENT	Sent	3
87	NDA	SIGNED	Signed	4
88	NDA	COMPLETED	Completed	5
89	NDA	REJECTED	Rejected	6
90	NDA	EXPIRED	Expired	7
\.


--
-- Data for Name: system_configuration; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.system_configuration (config_key, config_value, data_type, description, updated_by, updated_at) FROM stdin;
AUTO_APPROVAL_LIMIT	5000	NUMBER	Invoices at or below this amount (in base currency) skip manual approval if no other issues are raised	\N	2026-07-22 19:22:11.117003
DEFAULT_BASE_CURRENCY	INR	STRING	Company base currency for reporting and threshold comparisons	\N	2026-07-22 19:22:11.117003
DUPLICATE_INVOICE_WINDOW_DAYS	90	NUMBER	Lookback window for duplicate invoice_number + vendor_id detection	\N	2026-07-22 19:22:11.117003
GRN_MANDATORY	FALSE	BOOLEAN	Whether goods-based invoices require a matching GRN	\N	2026-07-22 19:22:11.117003
INVOICE_INTAKE_NOTIFICATION_EMAILS	Jagadish.Pannala@pavestechnologies.com	STRING	Email recipients for invoice vendor-not-found and vendor-auto-onboarding notifications	\N	2026-08-11 10:23:04.975024
OCR_CONFIDENCE_THRESHOLD	50	NUMBER	Minimum extraction_confidence (%) before an invoice is auto-promoted; below this, flagged for manual review	\N	2026-07-22 19:22:11.117003
PAYMENT_REMINDER_DAYS_BEFORE_DUE	3	NUMBER	Days before due_date to notify AP Executive of an unscheduled invoice	\N	2026-07-22 19:22:11.117003
PO_MANDATORY	FALSE	BOOLEAN	Whether every invoice must reference a PO	\N	2026-07-22 19:22:11.117003
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

COPY ap.tax_rule (tax_rule_id, rule_code, rule_name, tax_type_id, rule_category, description, priority, effective_from, effective_to, is_active, created_by, created_at, updated_by, updated_at, legal_reference, threshold_amount, threshold_type) FROM stdin;
1	GST_SAC_997331	GST for SAC 997331	1	GST_RATE	GST rate applicable for SAC 997331	100	2026-04-01	\N	t	\N	2026-08-19 09:36:53.714444	\N	2026-08-19 09:36:53.714444	\N	\N	\N
2	GST_SAC_998315	GST for SAC 998315	1	GST_RATE	GST rate applicable for SAC 998315	100	2026-04-01	\N	t	\N	2026-08-19 09:44:02.557072	\N	2026-08-19 09:44:02.557072	\N	\N	\N
3	CGST_9_SAME_STATE	CGST 9% - Intra State	5	TAX_COMPONENT	CGST applies when supplier and buyer are in the same state for applicable 18% GST supplies	100	2026-04-01	\N	t	\N	2026-08-19 09:44:44.779867	\N	2026-08-19 09:44:44.779867	\N	\N	\N
4	SGST_9_SAME_STATE	SGST 9% - Intra State	6	TAX_COMPONENT	SGST applies when supplier and buyer are in the same state for applicable 18% GST supplies	100	2026-04-01	\N	t	\N	2026-08-19 09:45:20.547435	\N	2026-08-19 09:45:20.547435	\N	\N	\N
5	IGST_18_DIFFERENT_STATE	IGST 18% - Inter State	7	TAX_COMPONENT	IGST applies when supplier and buyer are in different states for applicable 18% GST supplies	100	2026-04-01	\N	t	\N	2026-08-19 09:45:33.778154	\N	2026-08-19 09:45:33.778154	\N	\N	\N
6	TDS_194C	TDS - Contractor Payments	2	TDS_RATE	TDS applicable on payments to contractors/sub-contractors under Section 194C	100	2026-04-01	\N	t	\N	2026-08-21 14:29:27.17909	\N	2026-08-21 14:29:27.17909	Section 194C, Income-tax Act (FY2026-27)	100000.00	AGGREGATE_PERIOD
7	TDS_194J	TDS - Professional or Technical Services	2	TDS_RATE	TDS applicable on professional or technical service payments under Section 194J	100	2026-04-01	\N	t	\N	2026-08-21 14:29:27.17909	\N	2026-08-21 14:29:27.17909	Section 194J, Income-tax Act (FY2026-27)	30000.00	AGGREGATE_PERIOD
8	TDS_194I	TDS - Rent	2	TDS_RATE	TDS applicable on specified rent payments under Section 194I	100	2026-04-01	\N	t	\N	2026-08-21 14:29:27.17909	\N	2026-08-21 14:29:27.17909	Section 194I, Income-tax Act (FY2026-27)	240000.00	AGGREGATE_PERIOD
9	TDS_194H	TDS - Commission or Brokerage	2	TDS_RATE	TDS applicable on commission or brokerage payments under Section 194H	100	2026-04-01	\N	t	\N	2026-08-21 14:29:27.17909	\N	2026-08-21 14:29:27.17909	Section 194H, Income-tax Act (FY2026-27)	15000.00	AGGREGATE_PERIOD
10	TDS_194Q	TDS - Purchase of Goods	2	TDS_RATE	TDS applicable on specified purchases of goods under Section 194Q	100	2026-04-01	\N	t	\N	2026-08-21 14:29:27.17909	\N	2026-08-21 14:29:27.17909	Section 194Q, Income-tax Act (FY2026-27)	5000000.00	AGGREGATE_PERIOD
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
11	7	PAYMENT_NATURE	EQUALS	TECHNICAL_SERVICE	1	1	2026-09-23 11:52:38.545501	2026-09-23 11:52:38.545501
\.


--
-- Data for Name: tax_type; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.tax_type (tax_type_id, country_id, tax_name, tax_code, is_withholding, is_system_default, is_active, created_by, created_at, updated_by, updated_at) FROM stdin;
1	1	GST	GST	f	t	t	1	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
2	1	TDS	TDS	t	t	t	1	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
3	3	Standard VAT	VAT-STD	f	t	t	1	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
4	2	Sales Tax	SALES-TX	f	t	t	1	2026-07-22 19:22:11.117003	\N	2026-07-22 19:22:11.117003
5	1	CGST	CGST	f	t	t	\N	2026-08-14 04:52:57.208759	\N	2026-08-14 04:52:57.208759
6	1	SGST	SGST	f	t	t	\N	2026-08-14 04:52:57.208759	\N	2026-08-14 04:52:57.208759
7	1	IGST	IGST	f	t	t	\N	2026-08-14 04:52:57.208759	\N	2026-08-14 04:52:57.208759
\.


--
-- Data for Name: tds_payment_nature; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.tds_payment_nature (id, code, name, description, is_active, created_at, updated_at) FROM stdin;
1	CONTRACTOR	Contractor Payments	Payments made for contract or work execution services	t	2026-09-23 07:04:38.767154	2026-09-23 07:04:38.767154
2	PROFESSIONAL_SERVICE	Professional Services	Payments for professional services such as legal, accounting, consulting or similar services	t	2026-09-23 07:04:38.767154	2026-09-23 07:04:38.767154
3	TECHNICAL_SERVICE	Technical Services	Payments for technical, specialized or technical consultancy services	t	2026-09-23 07:04:38.767154	2026-09-23 07:04:38.767154
4	RENT	Rent	Payments towards rent of land, building, equipment or other applicable assets	t	2026-09-23 07:04:38.767154	2026-09-23 07:04:38.767154
5	COMMISSION	Commission or Brokerage	Payments towards commission, brokerage or similar intermediary services	t	2026-09-23 07:04:38.767154	2026-09-23 07:04:38.767154
6	PURCHASE_OF_GOODS	Purchase of Goods	Payments towards purchase of goods where TDS may apply	t	2026-09-23 07:04:38.767154	2026-09-23 07:04:38.767154
7	INTEREST	Interest	Interest payments other than specified exempt categories	t	2026-09-23 07:04:38.767154	2026-09-23 07:04:38.767154
8	OTHER	Other	Other payment natures requiring manual tax review	t	2026-09-23 07:04:38.767154	2026-09-23 07:04:38.767154
\.


--
-- Data for Name: ums_role_cache; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.ums_role_cache (role_id, role_name, raw_payload, source_ts_ms, synced_at) FROM stdin;
1	Super_Admin	{"role_id": 1, "role_name": "Super_Admin", "role_uuid": "0199bd8c-ef34-e3ca-ccec-000305ebc187", "created_at": "2025-10-07T01:52:34Z", "updated_at": "2026-05-19T06:26:20Z"}	1789455353911	2026-09-15 06:59:15.074975+00
2	Admin	{"role_id": 2, "role_name": "Admin", "role_uuid": "0199bd8c-ef38-99c9-a05c-e1fb00e287df", "created_at": "2025-10-07T01:52:34Z", "updated_at": "2025-10-07T01:52:34Z"}	1789455353912	2026-09-15 06:59:15.318464+00
3	HR	{"role_id": 3, "role_name": "HR", "role_uuid": "0199bd8c-ef39-041d-b455-74a03dc99ef5", "created_at": "2025-10-07T01:52:34Z", "updated_at": "2025-10-07T01:52:34Z"}	1789455353912	2026-09-15 06:59:15.502446+00
4	General	{"role_id": 4, "role_name": "General", "role_uuid": "0199bd8c-ef39-3435-71f3-1fc742bfac70", "created_at": "2025-10-07T01:52:34Z", "updated_at": "2025-10-07T01:52:34Z"}	1789455353912	2026-09-15 06:59:15.659321+00
7	Hr_Manager	{"role_id": 7, "role_name": "Hr_Manager", "role_uuid": "0199bd8c-ef3d-3de5-1904-a79ed0c4e0f5", "created_at": "2025-10-07T01:52:34Z", "updated_at": "2026-05-04T08:48:55Z"}	1789455353913	2026-09-15 06:59:15.833731+00
30	Project_Manager	{"role_id": 30, "role_name": "Project_Manager", "role_uuid": "019e07a5-8501-0adc-2da8-36133d8a06c8", "created_at": "2026-05-08T12:52:29Z", "updated_at": "2026-05-08T12:52:29Z"}	1789455353913	2026-09-15 06:59:16.005893+00
31	Reporting_Manager	{"role_id": 31, "role_name": "Reporting_Manager", "role_uuid": "019e07a5-aa2b-4acf-689a-4eeea91aeba5", "created_at": "2026-05-08T12:52:38Z", "updated_at": "2026-06-16T10:00:25Z"}	1789455353913	2026-09-15 06:59:16.17263+00
32	Resource_Manager	{"role_id": 32, "role_name": "Resource_Manager", "role_uuid": "019e07a7-6cf5-a7b4-483b-2987e3035500", "created_at": "2026-05-08T12:54:33Z", "updated_at": "2026-05-08T12:54:33Z"}	1789455353913	2026-09-15 06:59:16.383788+00
33	Delivery_Manager	{"role_id": 33, "role_name": "Delivery_Manager", "role_uuid": "019e07a7-bff7-c923-6627-1d1a21e879e4", "created_at": "2026-05-08T12:54:55Z", "updated_at": "2026-05-08T12:54:55Z"}	1789455353914	2026-09-15 06:59:16.533514+00
37	Tester	{"role_id": 37, "role_name": "Tester", "role_uuid": "019e1ba2-a1a9-e22c-56dd-9a6aad76b31d", "created_at": "2026-05-12T10:01:44Z", "updated_at": "2026-05-12T10:01:44Z"}	1789455353914	2026-09-15 06:59:16.687049+00
38	System	{"role_id": 38, "role_name": "System", "role_uuid": "019e91fd-0cda-c3b7-3b48-07b66d088af7", "created_at": "2026-06-04T09:35:41Z", "updated_at": "2026-06-04T09:35:41Z"}	1789455353914	2026-09-15 06:59:16.84428+00
39	HR_ADMIN	{"role_id": 39, "role_name": "HR_ADMIN", "role_uuid": "019f408f-b57d-9d5a-b146-266f014caf24", "created_at": "2026-07-08T07:09:48Z", "updated_at": "2026-07-08T07:09:48Z"}	1789455353915	2026-09-15 06:59:16.997045+00
40	HIRING_MANAGER	{"role_id": 40, "role_name": "HIRING_MANAGER", "role_uuid": "019f408f-f428-133b-c47d-7d2223d9844a", "created_at": "2026-07-08T07:10:04Z", "updated_at": "2026-07-08T07:10:04Z"}	1789455353915	2026-09-15 06:59:17.160804+00
41	RECRUITER	{"role_id": 41, "role_name": "RECRUITER", "role_uuid": "019f41be-c65a-9f3c-f1dd-ceb234fe45ca", "created_at": "2026-07-08T12:40:49Z", "updated_at": "2026-07-08T12:40:49Z"}	1789455353915	2026-09-15 06:59:17.350044+00
42	Vendor_Intake	{"role_id": 42, "role_name": "Vendor_Intake", "role_uuid": "019fd720-2106-ee19-01bd-529cd7b4f68b", "created_at": "2026-08-06T12:50:35Z", "updated_at": "2026-08-06T13:21:17Z"}	1789455353916	2026-09-15 06:59:17.527819+00
43	Finance_Executive	{"role_id": 43, "role_name": "Finance_Executive", "role_uuid": "01a01517-a53f-d129-7776-e82837f3d054", "created_at": "2026-08-18T13:37:46Z", "updated_at": "2026-08-18T13:37:46Z"}	1789455353916	2026-09-15 06:59:17.719357+00
44	Payment_Processor	{"role_id": 44, "role_name": "Payment_Processor", "role_uuid": "01a01960-c772-bedc-2454-7b14cf9c0434", "created_at": "2026-08-19T09:36:08Z", "updated_at": "2026-08-19T09:36:08Z"}	1789455353917	2026-09-15 06:59:17.889527+00
45	AP_EXECUTIVE	{"role_id": 45, "role_name": "AP_EXECUTIVE", "role_uuid": "01a01992-fb68-bd21-4167-088e2175ed9b", "created_at": "2026-08-19T10:30:58Z", "updated_at": "2026-08-20T06:05:30Z"}	1789455353917	2026-09-15 06:59:18.034575+00
46	Finance_Manager	{"role_id": 46, "role_name": "Finance_Manager", "role_uuid": "01a042e8-b828-6697-fb77-01becb19c0ca", "created_at": "2026-08-27T11:09:03Z", "updated_at": "2026-08-27T11:09:03Z"}	1789455353917	2026-09-15 06:59:18.207072+00
47	PR_Creator	{"role_id": 47, "role_name": "PR_Creator", "role_uuid": "01a07aaf-9678-0e79-412f-8b323162c3c7", "created_at": "2026-09-07T07:05:23Z", "updated_at": "2026-09-07T07:06:13Z"}	1789455353917	2026-09-15 06:59:18.368804+00
48	PR_Approver	{"role_id": 48, "role_name": "PR_Approver", "role_uuid": "01a07aaf-ce9d-1aa7-f619-42c22b263d67", "created_at": "2026-09-07T07:05:37Z", "updated_at": "2026-09-07T07:08:09Z"}	1789455353918	2026-09-15 06:59:18.562548+00
49	Procurement_Officer	{"role_id": 49, "role_name": "Procurement_Officer", "role_uuid": "01a07ab0-0eab-63b1-c11a-939b2c15dc4b", "created_at": "2026-09-07T07:05:54Z", "updated_at": "2026-09-07T07:05:54Z"}	1789455353918	2026-09-15 06:59:18.769444+00
50	TEST_CDC	{"role_id": 50, "role_name": "TEST_CDC", "role_uuid": "01a08b88-c659-0926-f095-8eaa4c78e27c", "created_at": "2026-09-10T13:36:32Z", "updated_at": "2026-09-10T13:36:32Z"}	1789455353918	2026-09-15 06:59:18.952475+00
\.


--
-- Data for Name: ums_user_cache; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.ums_user_cache (user_id, user_uuid, is_active, raw_payload, source_ts_ms, synced_at) FROM stdin;
1	0199bd8c-ef11-0ff0-1695-f2d12b5bcea2	t	{"mail": "admin.paves@pavestechnologies.com", "gender": "MALE", "contact": "+919100633231", "user_id": 1, "password": "$2b$12$WbNhPsi0Xfdms8Q/Z63/KewnNbEK6C4p021YVu/xWSLPCJCGqT8M2", "is_active": 1, "last_name": "Admin", "user_uuid": "0199bd8c-ef11-0ff0-1695-f2d12b5bcea2", "created_at": "2025-10-07T01:52:34Z", "first_name": "Paves", "updated_at": "2026-09-15T10:30:01Z", "employee_id": "5100001", "last_login_at": 1789468202000, "last_login_ip": "52.46.56.79", "password_last_updated": 1761716755000}	1789468201970	2026-09-15 10:50:18.883954+00
2	019e91fc-c2fd-0420-9cb1-29f5f71809bf	t	{"mail": "system.internal@pavestechnologies.com", "gender": "MALE", "contact": "+919059364400", "user_id": 2, "password": "$2b$12$z7jwTtoz7uRuf9G2BckyqOJNz.eBYsyq69S9mkyqAsmUFsanUsp.u", "is_active": 1, "last_name": "Internal", "user_uuid": "019e91fc-c2fd-0420-9cb1-29f5f71809bf", "created_at": "2026-06-04T09:35:25Z", "first_name": "System", "updated_at": "2026-09-15T06:49:23Z", "employee_id": null, "last_login_at": 1789454964000, "last_login_ip": "15.158.25.203", "password_last_updated": 1780566091000}	\N	2026-09-15 10:48:05.166779+00
5100002	019e8c6f-9735-2eba-21f1-56f5d79c3256	t	{"mail": "mohan.saladi@pavestechnologies.com", "gender": "MALE", "contact": "+919704622099", "user_id": 5100002, "password": "$2b$12$/mGnIu5s9rVQW7zXzd4JQubtNoee5BpGFWAHoFGJvIQbqJlsR2XaC", "is_active": 1, "last_name": "Saladi", "user_uuid": "019e8c6f-9735-2eba-21f1-56f5d79c3256", "created_at": "2026-06-03T07:45:51Z", "first_name": "Mohan Dharma Teja", "updated_at": "2026-06-09T07:14:30Z", "employee_id": "5100002", "last_login_at": 1780989271000, "last_login_ip": "52.46.56.79", "password_last_updated": 1780473198000}	\N	2026-09-15 07:29:54.224945+00
5100003	019e8c6f-9746-823d-0fd1-572e7ff403c8	t	{"mail": "thejas.gajula@pavestechnologies.com", "gender": "MALE", "contact": "+917330925101", "user_id": 5100003, "password": "$2b$12$qFRBvzaV1verNDaBhS7tSOT58nVbS2gONvgXV71XsV8MFnn2gtefu", "is_active": 1, "last_name": "Gajula", "user_uuid": "019e8c6f-9746-823d-0fd1-572e7ff403c8", "created_at": "2026-06-03T07:45:51Z", "first_name": "Thejas", "updated_at": "2026-06-03T07:51:32Z", "employee_id": "5100003", "last_login_at": null, "last_login_ip": null, "password_last_updated": null}	\N	2026-09-15 07:29:54.905375+00
5100005	019e8c6f-9754-6bc2-8378-21c15fe06b71	t	{"mail": "ajay.korada@pavestechnologies.com", "gender": "MALE", "contact": "+917981773241", "user_id": 5100005, "password": "$2b$12$1qYwbbTB8puM4JSDw5WE/.pFmUEUtsoRsuwZiwUqQr.T5.M7uEwJO", "is_active": 1, "last_name": "Korada", "user_uuid": "019e8c6f-9754-6bc2-8378-21c15fe06b71", "created_at": "2026-06-03T07:45:51Z", "first_name": "Ajay", "updated_at": "2026-09-10T06:28:24Z", "employee_id": "5100005", "last_login_at": 1789021705000, "last_login_ip": "52.46.56.79", "password_last_updated": 1780555505000}	\N	2026-09-15 07:29:55.479713+00
5100007	019e8c6f-97d0-6379-9078-0ba22e4ec921	t	{"mail": "venkatesh.gali@pavestechnologies.com", "gender": "MALE", "contact": "+919876534689", "user_id": 5100007, "password": "$2b$12$dUUPvR1gBnCESZH17dq4zu4F7pO5.6k4SMRbsBMbab3PS8mUz1Sue", "is_active": 1, "last_name": "Gali", "user_uuid": "019e8c6f-97d0-6379-9078-0ba22e4ec921", "created_at": "2026-06-03T07:45:51Z", "first_name": "Venkatesh", "updated_at": "2026-09-09T13:16:34Z", "employee_id": "5100007", "last_login_at": 1788959795000, "last_login_ip": "52.46.56.79", "password_last_updated": 1781589689000}	\N	2026-09-15 07:29:56.126932+00
5100008	019e8c6f-9763-00c7-b39c-59c56712443c	t	{"mail": "swarnaraj.alwala@pavestechnologies.com", "gender": "MALE", "contact": "+918096563083", "user_id": 5100008, "password": "$2b$12$dg0R5psjSQfPlZAV2XvhiukWHG76m7BCNzIaMdOzqK7LoMAKA73Ei", "is_active": 1, "last_name": "alwala", "user_uuid": "019e8c6f-9763-00c7-b39c-59c56712443c", "created_at": "2026-06-03T07:45:51Z", "first_name": "swaran raj", "updated_at": "2026-09-01T12:28:15Z", "employee_id": "5100008", "last_login_at": 1788265695000, "last_login_ip": "52.46.56.79", "password_last_updated": 1780479482000}	\N	2026-09-15 07:29:56.765787+00
5100009	019e68eb-06b3-ae1c-03d8-27e8949646eb	t	{"mail": "jagadish.pannala@pavestechnologies.com", "gender": "MALE", "contact": "+919100633230", "user_id": 5100009, "password": "$2b$12$2NYQSIbUNwto565lDHOpEuWt46imB9hpbeTjDoUs4EpTkVDmIydDi", "is_active": 1, "last_name": "Pannala", "user_uuid": "019e68eb-06b3-ae1c-03d8-27e8949646eb", "created_at": "2026-05-27T10:36:52Z", "first_name": "Jagadish", "updated_at": "2026-09-15T10:53:55Z", "employee_id": "5100009", "last_login_at": 1789469635000, "last_login_ip": "52.46.56.79", "password_last_updated": 1788259703000}	1789469635081	2026-09-15 10:53:55.375692+00
5100010	019e8c6f-9772-c412-1177-4759698bb1d6	t	{"mail": "sathwik.perka@pavestechnologies.com", "gender": "MALE", "contact": "+916309586236", "user_id": 5100010, "password": "$2b$12$/o/OV//MkIXKbJPkm/8a/esnzcLMpNbfzeePXw6fEq6hnG8iT4V8S", "is_active": 1, "last_name": "Perka", "user_uuid": "019e8c6f-9772-c412-1177-4759698bb1d6", "created_at": "2026-06-03T07:45:51Z", "first_name": "Sathwik", "updated_at": "2026-09-15T10:13:25Z", "employee_id": "5100010", "last_login_at": 1789467205000, "last_login_ip": "15.158.25.242", "password_last_updated": 1780554935000}	1789467205272	2026-09-15 10:50:15.676666+00
5100011	019e8c6f-97dc-c1a8-8790-1a2e9d1184a9	t	{"mail": "sricharan.chilkuri@pavestechnologies.com", "gender": "MALE", "contact": "+919346639366", "user_id": 5100011, "password": "$2b$12$Fxj8tZnEwdrCNpppjHuauO0Kdl26ICClGZjE5w/EopgWeJnj9HSvW", "is_active": 1, "last_name": "Chilkuri", "user_uuid": "019e8c6f-97dc-c1a8-8790-1a2e9d1184a9", "created_at": "2026-06-03T07:45:51Z", "first_name": "Sri Charan", "updated_at": "2026-07-10T07:26:31Z", "employee_id": "5100011", "last_login_at": 1783668391000, "last_login_ip": "130.176.104.148", "password_last_updated": null}	\N	2026-09-15 07:29:58.422001+00
5100012	019e8c6f-9781-e1a7-f161-74e0cfbca3cf	t	{"mail": "rangaswamy.dama@pavestechnologies.com", "gender": "MALE", "contact": "+919059582200", "user_id": 5100012, "password": "$2b$12$L7K7l5YU4e7hxGcwhrHNDOPUpfa87UU6m9DrOkfWYtFK.X8AHboMq", "is_active": 1, "last_name": "Dama", "user_uuid": "019e8c6f-9781-e1a7-f161-74e0cfbca3cf", "created_at": "2026-06-03T07:45:51Z", "first_name": "Rangaswamy", "updated_at": "2026-09-15T07:37:50Z", "employee_id": "5100012", "last_login_at": 1789457871000, "last_login_ip": "52.46.56.79", "password_last_updated": 1780479507000}	1789457870757	2026-09-15 07:37:50.740331+00
5100013	019e8c6f-978f-f260-6d86-d768ec44ba6d	t	{"mail": "ajay.bhukya@pavestechnologies.com", "gender": "MALE", "contact": "+919100633230", "user_id": 5100013, "password": "$2b$12$F2eQGDr0q29tvvVmDZ7jf.nlqljmXIp5Bb9I1/y/S1pCKH1MaCB5e", "is_active": 1, "last_name": "Bhukya", "user_uuid": "019e8c6f-978f-f260-6d86-d768ec44ba6d", "created_at": "2026-06-03T07:45:51Z", "first_name": "Ajay", "updated_at": "2026-09-11T05:21:43Z", "employee_id": "5100013", "last_login_at": 1789104104000, "last_login_ip": "3.172.97.201", "password_last_updated": 1780486778000}	\N	2026-09-15 07:29:59.531488+00
5100014	019e8c42-2660-4fd6-56c8-14bc05878344	t	{"mail": "sindhu.yanala@pavestechnologies.com", "gender": "MALE", "contact": "+917396774639", "user_id": 5100014, "password": "$2b$12$6g7Hb5seacuo3r5p9vSEueGDTO1pItu/8xfYMc7WEvt59eH1tpCBS", "is_active": 1, "last_name": "Yanala", "user_uuid": "019e8c42-2660-4fd6-56c8-14bc05878344", "created_at": "2026-06-03T07:08:52Z", "first_name": "Sindhu", "updated_at": "2026-09-15T06:57:26Z", "employee_id": "5100014", "last_login_at": 1789455447000, "last_login_ip": "3.172.97.232", "password_last_updated": 1780472439000}	\N	2026-09-15 07:30:15.177693+00
5100015	019e8c6f-979e-7e3e-8fa3-74a2d4a9edb6	t	{"mail": "rohit.lingarker@pavestechnologies.com", "gender": "MALE", "contact": "+917780294871", "user_id": 5100015, "password": "$2b$12$0jUqPMAgubc0QFdYLT38ouWhVOCqYWZM9nX4Z0Db8E9zU9ZTg15HO", "is_active": 1, "last_name": "lingarker", "user_uuid": "019e8c6f-979e-7e3e-8fa3-74a2d4a9edb6", "created_at": "2026-06-03T07:45:51Z", "first_name": "rohit", "updated_at": "2026-08-17T10:28:52Z", "employee_id": "5100015", "last_login_at": 1786962533000, "last_login_ip": "52.46.56.79", "password_last_updated": 1786948224000}	\N	2026-09-15 07:30:00.974218+00
5100017	019e8c6f-97aa-842e-cde0-72514e55edda	t	{"mail": "vijayadurga.balada@pavestechnologies.com", "gender": "MALE", "contact": "+917995041766", "user_id": 5100017, "password": "$2b$12$AOpOtxwNqRb3qowxN0ojOepklSTYDqCrApdyGr94gYX5V2Q2.b2um", "is_active": 1, "last_name": "Balada", "user_uuid": "019e8c6f-97aa-842e-cde0-72514e55edda", "created_at": "2026-06-03T07:45:51Z", "first_name": "vijayadurga", "updated_at": "2026-08-06T13:11:07Z", "employee_id": "5100017", "last_login_at": 1786021868000, "last_login_ip": "52.46.56.79", "password_last_updated": 1786021845000}	\N	2026-09-15 07:30:01.558789+00
5100020	019e8c6f-97b7-9061-d9d1-4704d264f454	t	{"mail": "aditya.bolli@pavestechnologies.com", "gender": "MALE", "contact": "+917815931935", "user_id": 5100020, "password": "$2b$12$cBmDqPHh3Z.EyNEEwvTKb.sgmJ/WV6UTvP2urHy77NaMwA5ivj/hK", "is_active": 1, "last_name": "Teja", "user_uuid": "019e8c6f-97b7-9061-d9d1-4704d264f454", "created_at": "2026-06-03T07:45:51Z", "first_name": "Bolli", "updated_at": "2026-09-15T10:14:13Z", "employee_id": "5100020", "last_login_at": 1789467254000, "last_login_ip": "15.158.25.242", "password_last_updated": 1780553635000}	1789467254008	2026-09-15 10:50:17.387678+00
5100021	019e8c6f-97c4-e62e-52b0-11b9e4816c88	t	{"mail": "niharika.kandukoori@pavestechnologies.com", "gender": "MALE", "contact": "+919502528882", "user_id": 5100021, "password": "$2b$12$tS05KC0GDRuumowBL5aPBePFCKjWF.APFfHm6XRj8CB4jtf6ydJ1i", "is_active": 1, "last_name": "Niharika", "user_uuid": "019e8c6f-97c4-e62e-52b0-11b9e4816c88", "created_at": "2026-06-03T07:45:51Z", "first_name": "Kandukoori", "updated_at": "2026-08-31T14:05:40Z", "employee_id": "5100021", "last_login_at": 1788185141000, "last_login_ip": "3.172.97.232", "password_last_updated": 1783590265000}	\N	2026-09-15 07:30:02.939278+00
5100022	019e8c6f-97e9-b9ea-8af9-06af6c630bea	t	{"mail": "venipriya.p@pavestechnologies.com", "gender": "MALE", "contact": "+911226354762", "user_id": 5100022, "password": "$2b$12$7IHiNjsmtHpr7dF/0qA6PeSMWLJNNTSNEgFvHz9G1Wn0d4l5TZxPu", "is_active": 1, "last_name": "P", "user_uuid": "019e8c6f-97e9-b9ea-8af9-06af6c630bea", "created_at": "2026-06-03T07:45:51Z", "first_name": "Veni Priya", "updated_at": "2026-09-10T10:20:59Z", "employee_id": "5100022", "last_login_at": 1788944240000, "last_login_ip": "52.46.56.79", "password_last_updated": 1789035659000}	\N	2026-09-15 07:30:03.590675+00
5100023	019e8c25-0e73-7147-6bda-1279601ab9b4	t	{"mail": "ramagopal.durgam@pavestechnologies.com", "gender": "MALE", "contact": "+918975645789", "user_id": 5100023, "password": "$2b$12$WbNhPsi0Xfdms8Q/Z63/KewnNbEK6C4p021YVu/xWSLPCJCGqT8M2", "is_active": 1, "last_name": "Durgam", "user_uuid": "019e8c25-0e73-7147-6bda-1279601ab9b4", "created_at": "2026-06-03T06:23:45Z", "first_name": "Rama", "updated_at": "2026-09-11T13:10:56Z", "employee_id": "5100023", "last_login_at": 1789132256000, "last_login_ip": "52.46.56.79", "password_last_updated": 1781862585000}	\N	2026-09-15 07:30:04.225272+00
5100024	019e8c6f-9812-9a50-5d66-fa4dca42de44	t	{"mail": "rakesh.k@pavestechnologies.com", "gender": "MALE", "contact": "+919876543210", "user_id": 5100024, "password": "$2b$12$eU7RdFLfLWwNBdw6wDPl9uP1RPRKzH42aXMzmXUZrJ/8xZ3Fm9Gaa", "is_active": 1, "last_name": "k", "user_uuid": "019e8c6f-9812-9a50-5d66-fa4dca42de44", "created_at": "2026-06-03T07:45:51Z", "first_name": "rakesh", "updated_at": "2026-09-10T10:18:50Z", "employee_id": "5100024", "last_login_at": 1789035530000, "last_login_ip": "52.46.56.79", "password_last_updated": 1788781435000}	\N	2026-09-15 07:30:04.820645+00
5100025	019e6973-3a4d-65c2-0b0a-34f73c5f18ee	t	{"mail": "sambi.eada@pavestechnologies.com", "gender": "MALE", "contact": "+14079699974", "user_id": 5100025, "password": "$2b$12$87W3ZykuVHlnTvn.tTYtIuoRBogCgWtFQ8QURq.Sx4VtxkvDiG1am", "is_active": 1, "last_name": "Eada", "user_uuid": "019e6973-3a4d-65c2-0b0a-34f73c5f18ee", "created_at": "2026-05-27T12:40:55Z", "first_name": "Sambi", "updated_at": "2026-06-03T07:52:40Z", "employee_id": "5100025", "last_login_at": null, "last_login_ip": null, "password_last_updated": null}	\N	2026-09-15 07:30:06.158822+00
5100026	019e8c6f-97f6-9cd6-2ecb-9bb7916d5ec4	t	{"mail": "bindub.usarti@pavestechnologies.com", "gender": "MALE", "contact": "+918328561719", "user_id": 5100026, "password": "$2b$12$fV68KSCE8I2mpnp0OBNL2uN177wMEJN9ACWxdGunMp9PNy3Upy9Ha", "is_active": 1, "last_name": "U", "user_uuid": "019e8c6f-97f6-9cd6-2ecb-9bb7916d5ec4", "created_at": "2026-06-03T07:45:51Z", "first_name": "Bindu Bhargavi", "updated_at": "2026-09-03T07:23:38Z", "employee_id": "5100026", "last_login_at": 1788420218000, "last_login_ip": "52.46.56.79", "password_last_updated": 1787829296000}	\N	2026-09-15 07:30:07.227026+00
5100027	019e8c6f-9805-1c42-431e-15c89a2f1ad8	t	{"mail": "kalasagar.p@pavestechnologies.com", "gender": "MALE", "contact": "+919381951224", "user_id": 5100027, "password": "$2b$12$ooeUbMKjnTk3.uFmpfops.IV6eT2pjMuAnCb8iMmGedcIwBXYylTW", "is_active": 1, "last_name": "P", "user_uuid": "019e8c6f-9805-1c42-431e-15c89a2f1ad8", "created_at": "2026-06-03T07:45:51Z", "first_name": "Kalasagar", "updated_at": "2026-09-04T07:19:16Z", "employee_id": "5100027", "last_login_at": 1788506356000, "last_login_ip": "15.158.2.75", "password_last_updated": 1787205428000}	\N	2026-09-15 07:30:07.912354+00
5100028	a858c3ff-9b6c-412f-8c64-b6803f817d9a	t	{"mail": "test.user@pavestechnologies.com", "gender": "MALE", "contact": "7396777850", "user_id": 5100028, "password": "$2b$12$Iar/aTAi7D4bOGqBzORWvuHwcVwIULGgoCiToIr2uY4eZ4clXlsMK", "is_active": 1, "last_name": "user", "user_uuid": "a858c3ff-9b6c-412f-8c64-b6803f817d9a", "created_at": "2026-06-16T13:32:30Z", "first_name": "Test", "updated_at": "2026-06-16T13:32:30Z", "employee_id": "5100028", "last_login_at": null, "last_login_ip": null, "password_last_updated": null}	\N	2026-09-15 07:30:08.485765+00
5100029	3e89bf42-0dda-4fc1-b67e-8590c0f444ad	t	{"mail": "sumiya.patha@pavestechnologies.com", "gender": "MALE", "contact": "+916302883868", "user_id": 5100029, "password": "$2b$12$Ps86jz3tdZc8Sm9PL9HmEOSI77S8SY6ooBmZqoNIbw5cJREA1pog2", "is_active": 1, "last_name": "pathan", "user_uuid": "3e89bf42-0dda-4fc1-b67e-8590c0f444ad", "created_at": "2026-06-16T13:32:30Z", "first_name": "sumiya", "updated_at": "2026-08-10T06:05:30Z", "employee_id": "5100029", "last_login_at": null, "last_login_ip": null, "password_last_updated": null}	\N	2026-09-15 07:30:09.296536+00
5100030	ae79c79e-40f7-4126-935d-2a37f6195f9c	t	{"mail": "sumu.pathan@pavestechnologies.com", "gender": "MALE", "contact": "+918989899998", "user_id": 5100030, "password": "$2b$12$DGWEMtMszUGYWiv3ZypB4O9hCLftx84ZjO7vwcg7RcHl0CjWJBUKC", "is_active": 1, "last_name": "pathan", "user_uuid": "ae79c79e-40f7-4126-935d-2a37f6195f9c", "created_at": "2026-06-16T13:32:30Z", "first_name": "sumu", "updated_at": "2026-08-10T06:04:27Z", "employee_id": "5100030", "last_login_at": null, "last_login_ip": null, "password_last_updated": null}	\N	2026-09-15 14:20:22.832437+00
5100031	019fd71e-2bd0-af39-7b38-0b2a511b201e	t	{"mail": "jagadishreddypannala6281@gmail.com", "gender": "MALE", "contact": "+919100633230", "user_id": 5100031, "password": "$2b$12$jJJQq3A6YBBsCgpRiyKvaeUNUSlUiSKCX4mFMA9ZTPr/eFi9BIp3i", "is_active": 1, "last_name": "Pannala", "user_uuid": "019fd71e-2bd0-af39-7b38-0b2a511b201e", "created_at": "2026-08-06T12:48:27Z", "first_name": "Jagadish Reddy", "updated_at": "2026-09-09T13:17:08Z", "employee_id": null, "last_login_at": 1788959829000, "last_login_ip": "52.46.56.79", "password_last_updated": 1787925918000}	\N	2026-09-15 14:20:23.428171+00
5100032	01a06627-8abd-15cf-8a40-11027aacd5f9	t	{"mail": "Abhishek.g@pavestechnologies.com", "gender": "MALE", "contact": "919391732446", "user_id": 5100032, "password": "$2b$12$pT7s/5zfdH9LeF5WYsIZzu9ftmoIw8imNox7JMBUcMYeo/cnA8xdq", "is_active": 1, "last_name": "GUDA", "user_uuid": "01a06627-8abd-15cf-8a40-11027aacd5f9", "created_at": "2026-09-03T07:24:23Z", "first_name": "Abhishek", "updated_at": "2026-09-04T13:45:03Z", "employee_id": null, "last_login_at": 1788529503000, "last_login_ip": "52.46.56.79", "password_last_updated": 1788420552000}	\N	2026-09-15 14:20:24.070942+00
5100033	01a06628-e2bb-6570-330f-e37ab1f83be8	t	{"mail": "Thrinadh.B@pavestechnologies.com", "gender": "MALE", "contact": "917671870668", "user_id": 5100033, "password": "$2b$12$J3vQpy0VoPfyMVSjyiGIluDjl/jfl0HvJZEld4L7fyp6px1zteVU6", "is_active": 1, "last_name": "Bhimavarapu", "user_uuid": "01a06628-e2bb-6570-330f-e37ab1f83be8", "created_at": "2026-09-03T07:25:51Z", "first_name": "Thrinadh Reddy", "updated_at": "2026-09-03T09:51:22Z", "employee_id": null, "last_login_at": 1788429082000, "last_login_ip": "127.0.0.1", "password_last_updated": 1788420697000}	\N	2026-09-15 14:20:24.676124+00
5100034	01a0668d-084c-2662-6532-efd5dac60ff9	t	{"mail": "abhishek.guda12@gmail.com", "gender": "MALE", "contact": "+919391732446", "user_id": 5100034, "password": "$2b$12$w7sny.l0egD/34Ox7XXHbeXwmh0MeD0ninfqVd9Kc5bHEYnRVwnUK", "is_active": 1, "last_name": "G", "user_uuid": "01a0668d-084c-2662-6532-efd5dac60ff9", "created_at": "2026-09-03T09:15:14Z", "first_name": "abhishek", "updated_at": "2026-09-04T06:44:31Z", "employee_id": null, "last_login_at": 1788427044000, "last_login_ip": "127.0.0.1", "password_last_updated": 1788427038000}	\N	2026-09-15 14:20:25.150426+00
5100035	01a066a2-3428-cb47-9c83-2c8834bcbc35	t	{"mail": "chinnuabhishek123@gmail.com", "gender": "MALE", "contact": "919391732446", "user_id": 5100035, "password": "$2b$12$sTJ7i1yFyH.SL6Xn.cO81OLitfcZxKV5fW8MZedi21wr0wq5uRNz.", "is_active": 1, "last_name": "Guda", "user_uuid": "01a066a2-3428-cb47-9c83-2c8834bcbc35", "created_at": "2026-09-03T09:38:21Z", "first_name": "abhi ", "updated_at": "2026-09-03T09:38:56Z", "employee_id": null, "last_login_at": 1788428337000, "last_login_ip": "127.0.0.1", "password_last_updated": null}	\N	2026-09-15 14:20:25.768835+00
5100036	01a06b23-3a83-55f9-1781-87f59ad9f9be	t	{"mail": "rangaswamy.dama@pavestachnologies.com", "gender": "MALE", "contact": "919391732446", "user_id": 5100036, "password": "$2b$12$7HFv6uxhdDc97Ew/IsrCMuCbdjmTsmbOZ4Zd53zmhJ1cvHNJ06GEu", "is_active": 1, "last_name": "swamy", "user_uuid": "01a06b23-3a83-55f9-1781-87f59ad9f9be", "created_at": "2026-09-04T06:37:46Z", "first_name": "Ranga", "updated_at": "2026-09-04T06:37:46Z", "employee_id": null, "last_login_at": null, "last_login_ip": null, "password_last_updated": null}	\N	2026-09-15 14:20:26.323582+00
5100037	01a06b2a-1760-d68a-b150-64da98bd16d5	t	{"mail": "abhishek.guda123@gmail.com", "gender": "MALE", "contact": "919391732446", "user_id": 5100037, "password": "$2b$12$XtMJFZPIp5xvXMKG6MYgguypjAssjIvsmq93HhovgI5E/MA5oK/Mi", "is_active": 1, "last_name": "Guda", "user_uuid": "01a06b2a-1760-d68a-b150-64da98bd16d5", "created_at": "2026-09-04T06:45:16Z", "first_name": "abhishek", "updated_at": "2026-09-04T13:44:49Z", "employee_id": null, "last_login_at": 1788529490000, "last_login_ip": "52.46.56.79", "password_last_updated": null}	\N	2026-09-15 14:20:26.870194+00
\.


--
-- Data for Name: unit_of_measure; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.unit_of_measure (id, code, name, category, allows_decimal, is_active, created_at, updated_at) FROM stdin;
1	EA	Each	COUNT	f	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
2	PCS	Piece	COUNT	f	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
3	UNIT	Unit	COUNT	f	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
4	SET	Set	COUNT	f	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
5	BOX	Box	PACKAGING	f	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
6	PACK	Pack	PACKAGING	f	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
7	CTN	Carton	PACKAGING	f	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
8	ROLL	Roll	PACKAGING	f	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
9	KG	Kilogram	WEIGHT	t	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
10	G	Gram	WEIGHT	t	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
11	M	Meter	LENGTH	t	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
12	CM	Centimeter	LENGTH	t	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
13	L	Liter	VOLUME	t	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
14	ML	Milliliter	VOLUME	t	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
15	SQM	Square Meter	AREA	t	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
16	SQFT	Square Foot	AREA	t	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
17	HR	Hour	TIME	t	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
18	DAY	Day	TIME	t	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
19	MON	Month	TIME	t	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
20	YR	Year	TIME	t	t	2026-09-08 11:37:19.031005	2026-09-08 11:37:19.031005
\.


--
-- Data for Name: vendor; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor (vendor_id, vendor_name, vendor_code, country_id, payment_term_id, currency_id, phone_number, email, status_id, created_by, created_at, updated_by, updated_at, pan_number) FROM stdin;
15	AMAZON WEB SERVICES INDIA PRIVATE LIMITED	AWSIPL0336	1	2	1	9100633230	kandukoori1919@gmail.com	2	5100031	2026-08-10 16:33:37.113797	5100031	2026-08-10 16:33:37.113797	AAJCA9880A
\.


--
-- Data for Name: vendor_address; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor_address (vendor_address_id, vendor_id, address_type, address_line1, address_line2, city, state, postal_code, country_id, is_primary, created_at, updated_at) FROM stdin;
11	15	REGISTERED	Block E	International Trade Tower, South Delhi	NEHRU PLACE	Delhi	110019	1	t	2026-08-10 16:33:37.822493	2026-08-10 16:33:37.822493
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

COPY ap.vendor_category_mapping (vendor_category_mapping_id, vendor_id, department_id, purchase_category_id, is_primary, pre_screen_status, created_at, updated_at, business_requirement, purpose_of_onboarding, pre_screen_result_reason, pre_screen_checked_at, nda_recommended, nda_override, nda_override_reason, nda_final_required, nda_decided_by, nda_decided_at, created_by, updated_by) FROM stdin;
\.


--
-- Data for Name: vendor_category_mapping_legacy; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor_category_mapping_legacy (vendor_category_mapping_id, vendor_id, vendor_category_id, is_primary, created_by, created_at, updated_by, updated_at) FROM stdin;
1	15	8	t	5100031	2026-08-31 10:04:29.583807	\N	2026-08-31 10:04:29.583807
\.


--
-- Data for Name: vendor_nda; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor_nda (nda_id, vendor_id, nda_required, nda_status_id, created_at, updated_at, pr_id, department_id, purchase_category_id, template_id, template_version, document_key, signed_document_key, recipient_email, valid_from, valid_until, sent_at, signed_at, completed_at, created_by, updated_by, content_version, content_updated_at, content_updated_by, content) FROM stdin;
\.


--
-- Data for Name: vendor_onboarding_request; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor_onboarding_request (id, pr_id, department_id, purchase_category_id, status_id, created_by, created_at, updated_at, business_requirement, purpose_of_onboarding, requested_vendor_name, requested_vendor_email, vendor_id, engagement_id, assigned_to, closed_at, updated_by) FROM stdin;
\.


--
-- Data for Name: vendor_screening_rule; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor_screening_rule (id, name, requires_nda, is_default, is_active, created_at, updated_at, department_id, purchase_category_id, description, created_by, updated_by) FROM stdin;
\.


--
-- Data for Name: vendor_tax; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor_tax (vendor_tax_id, registration_type, registration_number, is_verified, verified_at, created_at, vendor_address_id) FROM stdin;
10	GST	07AAJCA9880A1ZL	t	\N	2026-08-10 16:33:38.28736	11
\.


--
-- Data for Name: vendor_tds_profile; Type: TABLE DATA; Schema: ap; Owner: -
--

COPY ap.vendor_tds_profile (id, vendor_id, entity_type, residency_type, pan_status, lower_deduction_available, certificate_number, certificate_rate, certificate_valid_from, certificate_valid_to, tds_exemption_flag, exemption_reason, created_at, updated_at) FROM stdin;
1	15	COMPANY	RESIDENT	VALID	f	\N	\N	\N	\N	f	\N	2026-09-23 07:05:40.14801	2026-09-23 07:05:40.14801
\.


--
-- Name: (sequences) restart values
--

SELECT pg_catalog.setval('ap.approval_policy_id_seq', 2, true);
SELECT pg_catalog.setval('ap.approval_policy_level_id_seq', 36, true);
SELECT pg_catalog.setval('ap.approver_directory_id_seq', 50, true);
SELECT pg_catalog.setval('ap.audit_log_audit_log_id_seq', 654, true);
SELECT pg_catalog.setval('ap.cdc_failure_log_id_seq', 133, true);
SELECT pg_catalog.setval('ap.country_country_id_seq', 6, true);
SELECT pg_catalog.setval('ap.currency_currency_id_seq', 3, true);
SELECT pg_catalog.setval('ap.department_approver_id_seq', 1, false);
SELECT pg_catalog.setval('ap.department_id_seq', 6, true);
SELECT pg_catalog.setval('ap.goods_receipt_grn_id_seq', 14, true);
SELECT pg_catalog.setval('ap.goods_receipt_line_grn_line_id_seq', 16, true);
SELECT pg_catalog.setval('ap.inbound_document_inbound_document_id_seq', 123, true);
SELECT pg_catalog.setval('ap.invoice_approval_invoice_approval_id_seq', 1, true);
SELECT pg_catalog.setval('ap.invoice_approval_invoice_approval_id_seq1', 71, true);
SELECT pg_catalog.setval('ap.invoice_approval_step_approver_id_seq', 77, true);
SELECT pg_catalog.setval('ap.invoice_approval_step_id_seq', 71, true);
SELECT pg_catalog.setval('ap.invoice_attachment_invoice_attachment_id_seq', 95, true);
SELECT pg_catalog.setval('ap.invoice_invoice_id_seq', 104, true);
SELECT pg_catalog.setval('ap.invoice_issue_invoice_issue_id_seq', 6, true);
SELECT pg_catalog.setval('ap.invoice_line_invoice_line_id_seq', 218, true);
SELECT pg_catalog.setval('ap.nda_template_id_seq', 1, true);
SELECT pg_catalog.setval('ap.payment_invoice_payment_invoice_id_seq', 1, false);
SELECT pg_catalog.setval('ap.payment_payment_id_seq', 1, false);
SELECT pg_catalog.setval('ap.payment_term_payment_term_id_seq', 5, true);
SELECT pg_catalog.setval('ap.purchase_category_id_seq', 7, true);
SELECT pg_catalog.setval('ap.purchase_order_id_seq', 12, true);
SELECT pg_catalog.setval('ap.purchase_order_line_id_seq', 13, true);
SELECT pg_catalog.setval('ap.purchase_requisition_id_seq', 66, true);
SELECT pg_catalog.setval('ap.purchase_requisition_line_id_seq', 75, true);
SELECT pg_catalog.setval('ap.quotation_id_seq', 23, true);
SELECT pg_catalog.setval('ap.rfq_id_seq', 56, true);
SELECT pg_catalog.setval('ap.rfq_vendor_id_seq', 103, true);
SELECT pg_catalog.setval('ap.status_master_status_id_seq', 90, true);
SELECT pg_catalog.setval('ap.tax_rate_rule_tax_rate_rule_id_seq', 10, true);
SELECT pg_catalog.setval('ap.tax_rule_condition_tax_rule_condition_id_seq', 11, true);
SELECT pg_catalog.setval('ap.tax_rule_tax_rule_id_seq', 10, true);
SELECT pg_catalog.setval('ap.tax_type_tax_type_id_seq', 7, true);
SELECT pg_catalog.setval('ap.ums_role_cache_role_id_seq', 1, false);
SELECT pg_catalog.setval('ap.ums_user_cache_user_id_seq', 1, false);
SELECT pg_catalog.setval('ap.unit_of_measure_id_seq', 40, true);
SELECT pg_catalog.setval('ap.vendor_address_vendor_address_id_seq', 86, true);
SELECT pg_catalog.setval('ap.vendor_bank_vendor_bank_id_seq', 7, true);
SELECT pg_catalog.setval('ap.vendor_category_mapping_vendor_category_mapping_id_seq', 73, true);
SELECT pg_catalog.setval('ap.vendor_nda_nda_id_seq', 6, true);
SELECT pg_catalog.setval('ap.vendor_onboarding_request_id_seq', 70, true);
SELECT pg_catalog.setval('ap.vendor_screening_rule_id_seq', 1, false);
SELECT pg_catalog.setval('ap.vendor_tax_vendor_tax_id_seq', 46, true);
SELECT pg_catalog.setval('ap.vendor_vendor_id_seq', 90, true);
--
-- Name: approval_policy_level approval_policy_level_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approval_policy_level
    ADD CONSTRAINT approval_policy_level_pkey PRIMARY KEY (id);


--
-- Name: approval_policy_level approval_policy_level_policy_id_level_number_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approval_policy_level
    ADD CONSTRAINT approval_policy_level_policy_id_level_number_key UNIQUE (approval_policy_id, level_number);


--
-- Name: approval_policy approval_policy_name_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approval_policy
    ADD CONSTRAINT approval_policy_name_key UNIQUE (name);


--
-- Name: approval_policy approval_policy_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approval_policy
    ADD CONSTRAINT approval_policy_pkey PRIMARY KEY (id);


--
-- Name: approver_directory approver_directory_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approver_directory
    ADD CONSTRAINT approver_directory_pkey PRIMARY KEY (id);


--
-- Name: approver_directory_role approver_directory_role_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approver_directory_role
    ADD CONSTRAINT approver_directory_role_pkey PRIMARY KEY (id);


--
-- Name: approver_directory_role approver_directory_role_user_role_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approver_directory_role
    ADD CONSTRAINT approver_directory_role_user_role_key UNIQUE (user_uuid, role_id);


--
-- Name: approver_directory approver_directory_user_uuid_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approver_directory
    ADD CONSTRAINT approver_directory_user_uuid_key UNIQUE (user_uuid);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (audit_log_id);


--
-- Name: cdc_failure_log cdc_failure_log_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.cdc_failure_log
    ADD CONSTRAINT cdc_failure_log_pkey PRIMARY KEY (id);


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
-- Name: department_approver department_approver_department_id_user_uuid_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.department_approver
    ADD CONSTRAINT department_approver_department_id_user_uuid_key UNIQUE (department_id, user_uuid);


--
-- Name: department_approver department_approver_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.department_approver
    ADD CONSTRAINT department_approver_pkey PRIMARY KEY (id);


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
-- Name: eos_department_cache eos_department_cache_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.eos_department_cache
    ADD CONSTRAINT eos_department_cache_pkey PRIMARY KEY (department_uuid);


--
-- Name: eos_employee_cache eos_employee_cache_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.eos_employee_cache
    ADD CONSTRAINT eos_employee_cache_pkey PRIMARY KEY (employee_uuid);


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
-- Name: invoice_approval_legacy invoice_approval_legacy_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_legacy
    ADD CONSTRAINT invoice_approval_legacy_pkey PRIMARY KEY (invoice_approval_id);


--
-- Name: invoice_approval invoice_approval_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval
    ADD CONSTRAINT invoice_approval_pkey PRIMARY KEY (invoice_approval_id);


--
-- Name: invoice_approval_step invoice_approval_step_approval_id_level_number_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_step
    ADD CONSTRAINT invoice_approval_step_approval_id_level_number_key UNIQUE (invoice_approval_id, level_number);


--
-- Name: invoice_approval_step_approver invoice_approval_step_approver_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_step_approver
    ADD CONSTRAINT invoice_approval_step_approver_pkey PRIMARY KEY (id);


--
-- Name: invoice_approval_step_approver invoice_approval_step_approver_step_id_user_uuid_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_step_approver
    ADD CONSTRAINT invoice_approval_step_approver_step_id_user_uuid_key UNIQUE (approval_step_id, user_uuid);


--
-- Name: invoice_approval_step invoice_approval_step_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_step
    ADD CONSTRAINT invoice_approval_step_pkey PRIMARY KEY (id);


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
-- Name: invoice_tds invoice_tds_invoice_unique; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_tds
    ADD CONSTRAINT invoice_tds_invoice_unique UNIQUE (invoice_id);


--
-- Name: invoice_tds invoice_tds_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_tds
    ADD CONSTRAINT invoice_tds_pkey PRIMARY KEY (id);


--
-- Name: invoice invoice_vendor_id_invoice_number_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_vendor_id_invoice_number_key UNIQUE (vendor_id, invoice_number);


--
-- Name: nda_template nda_template_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.nda_template
    ADD CONSTRAINT nda_template_code_key UNIQUE (code);


--
-- Name: nda_template nda_template_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.nda_template
    ADD CONSTRAINT nda_template_pkey PRIMARY KEY (id);


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
-- Name: purchase_category_tds_mapping purchase_category_tds_mapping_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_category_tds_mapping
    ADD CONSTRAINT purchase_category_tds_mapping_pkey PRIMARY KEY (id);


--
-- Name: purchase_category_tds_mapping purchase_category_tds_mapping_unique; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_category_tds_mapping
    ADD CONSTRAINT purchase_category_tds_mapping_unique UNIQUE (purchase_category_id, tds_payment_nature_id);


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
-- Name: rfq rfq_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.rfq
    ADD CONSTRAINT rfq_pkey PRIMARY KEY (id);


--
-- Name: rfq rfq_rfq_number_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.rfq
    ADD CONSTRAINT rfq_rfq_number_key UNIQUE (rfq_number);


--
-- Name: rfq_vendor rfq_vendor_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.rfq_vendor
    ADD CONSTRAINT rfq_vendor_pkey PRIMARY KEY (id);


--
-- Name: rfq_vendor rfq_vendor_rfq_id_vendor_id_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.rfq_vendor
    ADD CONSTRAINT rfq_vendor_rfq_id_vendor_id_key UNIQUE (rfq_id, vendor_id);


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
-- Name: tax_type tax_type_country_id_tax_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_type
    ADD CONSTRAINT tax_type_country_id_tax_code_key UNIQUE (country_id, tax_code);


--
-- Name: tax_type tax_type_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tax_type
    ADD CONSTRAINT tax_type_pkey PRIMARY KEY (tax_type_id);


--
-- Name: tds_payment_nature tds_payment_nature_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tds_payment_nature
    ADD CONSTRAINT tds_payment_nature_code_key UNIQUE (code);


--
-- Name: tds_payment_nature tds_payment_nature_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.tds_payment_nature
    ADD CONSTRAINT tds_payment_nature_pkey PRIMARY KEY (id);


--
-- Name: ums_role_cache ums_role_cache_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.ums_role_cache
    ADD CONSTRAINT ums_role_cache_pkey PRIMARY KEY (role_id);


--
-- Name: ums_user_cache ums_user_cache_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.ums_user_cache
    ADD CONSTRAINT ums_user_cache_pkey PRIMARY KEY (user_id);


--
-- Name: unit_of_measure unit_of_measure_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.unit_of_measure
    ADD CONSTRAINT unit_of_measure_code_key UNIQUE (code);


--
-- Name: unit_of_measure unit_of_measure_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.unit_of_measure
    ADD CONSTRAINT unit_of_measure_pkey PRIMARY KEY (id);


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
-- Name: vendor_category_mapping_legacy vendor_category_mapping_legacy_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping_legacy
    ADD CONSTRAINT vendor_category_mapping_legacy_pkey PRIMARY KEY (vendor_category_mapping_id);


--
-- Name: vendor_category_mapping_legacy vendor_category_mapping_legacy_unique; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping_legacy
    ADD CONSTRAINT vendor_category_mapping_legacy_unique UNIQUE (vendor_id, vendor_category_id);


--
-- Name: vendor_category_mapping vendor_category_mapping_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping
    ADD CONSTRAINT vendor_category_mapping_pkey PRIMARY KEY (vendor_category_mapping_id);


--
-- Name: vendor_category vendor_category_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category
    ADD CONSTRAINT vendor_category_pkey PRIMARY KEY (vendor_category_id);


--
-- Name: vendor_category_mapping vendor_engagement_unique; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping
    ADD CONSTRAINT vendor_engagement_unique UNIQUE (vendor_id, department_id, purchase_category_id);


--
-- Name: vendor_nda vendor_nda_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_nda
    ADD CONSTRAINT vendor_nda_pkey PRIMARY KEY (nda_id);


--
-- Name: vendor_onboarding_request vendor_onboarding_request_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_onboarding_request
    ADD CONSTRAINT vendor_onboarding_request_pkey PRIMARY KEY (id);


--
-- Name: vendor vendor_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_pkey PRIMARY KEY (vendor_id);


--
-- Name: vendor_screening_rule vendor_screening_rule_name_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_screening_rule
    ADD CONSTRAINT vendor_screening_rule_name_key UNIQUE (name);


--
-- Name: vendor_screening_rule vendor_screening_rule_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_screening_rule
    ADD CONSTRAINT vendor_screening_rule_pkey PRIMARY KEY (id);


--
-- Name: vendor_tax vendor_tax_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_tax
    ADD CONSTRAINT vendor_tax_pkey PRIMARY KEY (vendor_tax_id);


--
-- Name: vendor_tax vendor_tax_vendor_address_id_registration_type_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_tax
    ADD CONSTRAINT vendor_tax_vendor_address_id_registration_type_key UNIQUE (vendor_address_id, registration_type);


--
-- Name: vendor_tds_profile vendor_tds_profile_pkey; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_tds_profile
    ADD CONSTRAINT vendor_tds_profile_pkey PRIMARY KEY (id);


--
-- Name: vendor_tds_profile vendor_tds_profile_vendor_unique; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_tds_profile
    ADD CONSTRAINT vendor_tds_profile_vendor_unique UNIQUE (vendor_id);


--
-- Name: vendor vendor_vendor_code_key; Type: CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor
    ADD CONSTRAINT vendor_vendor_code_key UNIQUE (vendor_code);


--
-- Name: idx_approval_policy_category; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_approval_policy_category ON ap.approval_policy USING btree (purchase_category_id);


--
-- Name: idx_approval_policy_department; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_approval_policy_department ON ap.approval_policy USING btree (department_id);


--
-- Name: idx_audit_log_changed_at; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_audit_log_changed_at ON ap.audit_log USING btree (changed_at);


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
-- Name: idx_invoice_approval_legacy_invoice; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_invoice_approval_legacy_invoice ON ap.invoice_approval_legacy USING btree (invoice_id);


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
-- Name: idx_invoice_tds_invoice; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_invoice_tds_invoice ON ap.invoice_tds USING btree (invoice_id);


--
-- Name: idx_invoice_tds_rule; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_invoice_tds_rule ON ap.invoice_tds USING btree (tds_rule_id);


--
-- Name: idx_invoice_tds_status; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_invoice_tds_status ON ap.invoice_tds USING btree (determination_status);


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
-- Name: idx_purchase_category_department; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_purchase_category_department ON ap.purchase_category USING btree (department_id);


--
-- Name: idx_purchase_category_tds_mapping_category; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_purchase_category_tds_mapping_category ON ap.purchase_category_tds_mapping USING btree (purchase_category_id);


--
-- Name: idx_purchase_category_tds_mapping_nature; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_purchase_category_tds_mapping_nature ON ap.purchase_category_tds_mapping USING btree (tds_payment_nature_id);


--
-- Name: idx_quotation_pr; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_quotation_pr ON ap.quotation USING btree (pr_id);


--
-- Name: idx_quotation_rfq; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_quotation_rfq ON ap.quotation USING btree (rfq_id);


--
-- Name: idx_quotation_status; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_quotation_status ON ap.quotation USING btree (status_id);


--
-- Name: idx_quotation_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_quotation_vendor ON ap.quotation USING btree (vendor_id);


--
-- Name: idx_rfq_pr; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_rfq_pr ON ap.rfq USING btree (pr_id);


--
-- Name: idx_rfq_status; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_rfq_status ON ap.rfq USING btree (status_id);


--
-- Name: idx_rfq_vendor_rfq; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_rfq_vendor_rfq ON ap.rfq_vendor USING btree (rfq_id);


--
-- Name: idx_rfq_vendor_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_rfq_vendor_vendor ON ap.rfq_vendor USING btree (vendor_id);


--
-- Name: idx_tds_payment_nature_active; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_tds_payment_nature_active ON ap.tds_payment_nature USING btree (is_active);


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
-- Name: idx_vendor_engagement_category; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_engagement_category ON ap.vendor_category_mapping USING btree (purchase_category_id);


--
-- Name: idx_vendor_engagement_department; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_engagement_department ON ap.vendor_category_mapping USING btree (department_id);


--
-- Name: idx_vendor_nda_pr; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_nda_pr ON ap.vendor_nda USING btree (pr_id);


--
-- Name: idx_vendor_nda_scope; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_nda_scope ON ap.vendor_nda USING btree (vendor_id, department_id, purchase_category_id);


--
-- Name: idx_vendor_nda_status; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_nda_status ON ap.vendor_nda USING btree (nda_status_id);


--
-- Name: idx_vendor_nda_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_nda_vendor ON ap.vendor_nda USING btree (vendor_id);


--
-- Name: idx_vendor_screening_rule_category; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_screening_rule_category ON ap.vendor_screening_rule USING btree (purchase_category_id);


--
-- Name: idx_vendor_screening_rule_department; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_screening_rule_department ON ap.vendor_screening_rule USING btree (department_id);


--
-- Name: idx_vendor_status; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_status ON ap.vendor USING btree (status_id);


--
-- Name: idx_vendor_tds_profile_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vendor_tds_profile_vendor ON ap.vendor_tds_profile USING btree (vendor_id);


--
-- Name: idx_vor_assigned_to; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vor_assigned_to ON ap.vendor_onboarding_request USING btree (assigned_to);


--
-- Name: idx_vor_pr; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vor_pr ON ap.vendor_onboarding_request USING btree (pr_id);


--
-- Name: idx_vor_status; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vor_status ON ap.vendor_onboarding_request USING btree (status_id);


--
-- Name: idx_vor_vendor; Type: INDEX; Schema: ap; Owner: -
--

CREATE INDEX idx_vor_vendor ON ap.vendor_onboarding_request USING btree (vendor_id);


--
-- Name: approver_directory update_approver_directory_modtime; Type: TRIGGER; Schema: ap; Owner: -
--

CREATE TRIGGER update_approver_directory_modtime BEFORE UPDATE ON ap.approver_directory FOR EACH ROW EXECUTE FUNCTION ap.update_modified_column();


--
-- Name: approval_policy fk_approval_policy_department; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approval_policy
    ADD CONSTRAINT fk_approval_policy_department FOREIGN KEY (department_id) REFERENCES ap.department(id);


--
-- Name: approval_policy_level fk_approval_policy_level_policy; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approval_policy_level
    ADD CONSTRAINT fk_approval_policy_level_policy FOREIGN KEY (approval_policy_id) REFERENCES ap.approval_policy(id) ON DELETE CASCADE;


--
-- Name: approval_policy fk_approval_policy_purchase_category; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.approval_policy
    ADD CONSTRAINT fk_approval_policy_purchase_category FOREIGN KEY (purchase_category_id) REFERENCES ap.purchase_category(id);


--
-- Name: department_approver fk_department_approver_department; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.department_approver
    ADD CONSTRAINT fk_department_approver_department FOREIGN KEY (department_id) REFERENCES ap.department(id) ON DELETE CASCADE;


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
-- Name: invoice_approval fk_invoice_approval_policy; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval
    ADD CONSTRAINT fk_invoice_approval_policy FOREIGN KEY (approval_policy_id) REFERENCES ap.approval_policy(id);


--
-- Name: invoice_approval_step fk_invoice_approval_step_approval; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_step
    ADD CONSTRAINT fk_invoice_approval_step_approval FOREIGN KEY (invoice_approval_id) REFERENCES ap.invoice_approval(invoice_approval_id) ON DELETE CASCADE;


--
-- Name: invoice_approval_step_approver fk_invoice_approval_step_approver_step; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_step_approver
    ADD CONSTRAINT fk_invoice_approval_step_approver_step FOREIGN KEY (approval_step_id) REFERENCES ap.invoice_approval_step(id) ON DELETE CASCADE;


--
-- Name: invoice_approval_step fk_invoice_approval_step_department; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_step
    ADD CONSTRAINT fk_invoice_approval_step_department FOREIGN KEY (department_id) REFERENCES ap.department(id);


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
-- Name: purchase_category fk_purchase_category_department; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_category
    ADD CONSTRAINT fk_purchase_category_department FOREIGN KEY (department_id) REFERENCES ap.department(id);


--
-- Name: quotation fk_quotation_pr; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.quotation
    ADD CONSTRAINT fk_quotation_pr FOREIGN KEY (pr_id) REFERENCES ap.purchase_requisition(id) ON DELETE CASCADE;


--
-- Name: quotation fk_quotation_rfq; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.quotation
    ADD CONSTRAINT fk_quotation_rfq FOREIGN KEY (rfq_id) REFERENCES ap.rfq(id) ON DELETE SET NULL;


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
-- Name: rfq fk_rfq_pr; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.rfq
    ADD CONSTRAINT fk_rfq_pr FOREIGN KEY (pr_id) REFERENCES ap.purchase_requisition(id) ON DELETE CASCADE;


--
-- Name: rfq fk_rfq_status; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.rfq
    ADD CONSTRAINT fk_rfq_status FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: rfq_vendor fk_rfq_vendor_rfq; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.rfq_vendor
    ADD CONSTRAINT fk_rfq_vendor_rfq FOREIGN KEY (rfq_id) REFERENCES ap.rfq(id) ON DELETE CASCADE;


--
-- Name: rfq_vendor fk_rfq_vendor_vendor; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.rfq_vendor
    ADD CONSTRAINT fk_rfq_vendor_vendor FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: vendor_nda fk_vendor_nda_category; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_nda
    ADD CONSTRAINT fk_vendor_nda_category FOREIGN KEY (purchase_category_id) REFERENCES ap.purchase_category(id);


--
-- Name: vendor_nda fk_vendor_nda_department; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_nda
    ADD CONSTRAINT fk_vendor_nda_department FOREIGN KEY (department_id) REFERENCES ap.department(id);


--
-- Name: vendor_nda fk_vendor_nda_pr; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_nda
    ADD CONSTRAINT fk_vendor_nda_pr FOREIGN KEY (pr_id) REFERENCES ap.purchase_requisition(id);


--
-- Name: vendor_nda fk_vendor_nda_status; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_nda
    ADD CONSTRAINT fk_vendor_nda_status FOREIGN KEY (nda_status_id) REFERENCES ap.status_master(status_id);


--
-- Name: vendor_nda fk_vendor_nda_template; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_nda
    ADD CONSTRAINT fk_vendor_nda_template FOREIGN KEY (template_id) REFERENCES ap.nda_template(id);


--
-- Name: vendor_nda fk_vendor_nda_vendor; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_nda
    ADD CONSTRAINT fk_vendor_nda_vendor FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


--
-- Name: vendor_screening_rule fk_vendor_screening_rule_category; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_screening_rule
    ADD CONSTRAINT fk_vendor_screening_rule_category FOREIGN KEY (purchase_category_id) REFERENCES ap.purchase_category(id);


--
-- Name: vendor_screening_rule fk_vendor_screening_rule_department; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_screening_rule
    ADD CONSTRAINT fk_vendor_screening_rule_department FOREIGN KEY (department_id) REFERENCES ap.department(id);


--
-- Name: vendor_onboarding_request fk_vor_department; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_onboarding_request
    ADD CONSTRAINT fk_vor_department FOREIGN KEY (department_id) REFERENCES ap.department(id);


--
-- Name: vendor_onboarding_request fk_vor_engagement; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_onboarding_request
    ADD CONSTRAINT fk_vor_engagement FOREIGN KEY (engagement_id) REFERENCES ap.vendor_category_mapping(vendor_category_mapping_id);


--
-- Name: vendor_onboarding_request fk_vor_pr; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_onboarding_request
    ADD CONSTRAINT fk_vor_pr FOREIGN KEY (pr_id) REFERENCES ap.purchase_requisition(id);


--
-- Name: vendor_onboarding_request fk_vor_purchase_category; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_onboarding_request
    ADD CONSTRAINT fk_vor_purchase_category FOREIGN KEY (purchase_category_id) REFERENCES ap.purchase_category(id);


--
-- Name: vendor_onboarding_request fk_vor_status; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_onboarding_request
    ADD CONSTRAINT fk_vor_status FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: vendor_onboarding_request fk_vor_vendor; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_onboarding_request
    ADD CONSTRAINT fk_vor_vendor FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


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
-- Name: invoice_approval_legacy invoice_approval_legacy_invoice_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_legacy
    ADD CONSTRAINT invoice_approval_legacy_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id) ON DELETE CASCADE;


--
-- Name: invoice_approval_legacy invoice_approval_legacy_invoice_issue_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_approval_legacy
    ADD CONSTRAINT invoice_approval_legacy_invoice_issue_id_fkey FOREIGN KEY (invoice_issue_id) REFERENCES ap.invoice_issue(invoice_issue_id);


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
-- Name: invoice invoice_department_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_department_id_fkey FOREIGN KEY (department_id) REFERENCES ap.department(id);


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
-- Name: invoice invoice_purchase_category_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_purchase_category_id_fkey FOREIGN KEY (purchase_category_id) REFERENCES ap.purchase_category(id);


--
-- Name: invoice invoice_status_id_fkey; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice
    ADD CONSTRAINT invoice_status_id_fkey FOREIGN KEY (status_id) REFERENCES ap.status_master(status_id);


--
-- Name: invoice_tds invoice_tds_invoice_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_tds
    ADD CONSTRAINT invoice_tds_invoice_fk FOREIGN KEY (invoice_id) REFERENCES ap.invoice(invoice_id) ON DELETE CASCADE;


--
-- Name: invoice_tds invoice_tds_payment_nature_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_tds
    ADD CONSTRAINT invoice_tds_payment_nature_fk FOREIGN KEY (payment_nature_id) REFERENCES ap.tds_payment_nature(id) ON DELETE RESTRICT;


--
-- Name: invoice_tds invoice_tds_rate_rule_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_tds
    ADD CONSTRAINT invoice_tds_rate_rule_fk FOREIGN KEY (tds_rate_rule_id) REFERENCES ap.tax_rate_rule(tax_rate_rule_id) ON DELETE RESTRICT;


--
-- Name: invoice_tds invoice_tds_rule_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.invoice_tds
    ADD CONSTRAINT invoice_tds_rule_fk FOREIGN KEY (tds_rule_id) REFERENCES ap.tax_rule(tax_rule_id) ON DELETE RESTRICT;


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
-- Name: purchase_category_tds_mapping purchase_category_tds_mapping_category_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_category_tds_mapping
    ADD CONSTRAINT purchase_category_tds_mapping_category_fk FOREIGN KEY (purchase_category_id) REFERENCES ap.purchase_category(id) ON DELETE CASCADE;


--
-- Name: purchase_category_tds_mapping purchase_category_tds_mapping_nature_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.purchase_category_tds_mapping
    ADD CONSTRAINT purchase_category_tds_mapping_nature_fk FOREIGN KEY (tds_payment_nature_id) REFERENCES ap.tds_payment_nature(id) ON DELETE RESTRICT;


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
-- Name: vendor_category_mapping_legacy vendor_category_mapping_legacy_category_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping_legacy
    ADD CONSTRAINT vendor_category_mapping_legacy_category_fk FOREIGN KEY (vendor_category_id) REFERENCES ap.vendor_category(vendor_category_id);


--
-- Name: vendor_category_mapping_legacy vendor_category_mapping_legacy_vendor_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping_legacy
    ADD CONSTRAINT vendor_category_mapping_legacy_vendor_fk FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id);


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
-- Name: vendor_category_mapping vendor_engagement_department_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping
    ADD CONSTRAINT vendor_engagement_department_fk FOREIGN KEY (department_id) REFERENCES ap.department(id);


--
-- Name: vendor_category_mapping vendor_engagement_purchase_category_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_category_mapping
    ADD CONSTRAINT vendor_engagement_purchase_category_fk FOREIGN KEY (purchase_category_id) REFERENCES ap.purchase_category(id);


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
-- Name: vendor_tds_profile vendor_tds_profile_vendor_fk; Type: FK CONSTRAINT; Schema: ap; Owner: -
--

ALTER TABLE ONLY ap.vendor_tds_profile
    ADD CONSTRAINT vendor_tds_profile_vendor_fk FOREIGN KEY (vendor_id) REFERENCES ap.vendor(vendor_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


