import enum
import json
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, DateTime,
    Text, ForeignKey, Enum as SAEnum, Date
)
from sqlalchemy.orm import relationship
from app.database import Base


class SegmentEnum(str, enum.Enum):
    micro = "micro"
    prof = "prof"
    multi = "multi"
    mfg = "mfg"


class KYCStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class QuoteStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"


class OrderStatus(str, enum.Enum):
    ORDER_CONFIRMED = "Order Confirmed"
    KYC_VERIFIED = "KYC Verified"
    ORDER_APPROVED = "Order Approved"
    FIBER_DISPATCHED = "Fiber Dispatched"
    ENGINEER_SCHEDULED = "Engineer Scheduled"
    INSTALLATION = "Installation"
    ACTIVATED = "Activated"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(String(50), default="customer")  # customer | partner | admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="user", uselist=False)
    partner = relationship("ChannelPartner", back_populates="user", uselist=False)


class Business(Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=False)
    business_type = Column(String(100))
    segment = Column(String(50))  # micro|prof|multi|mfg
    city = Column(String(100))
    city_tier = Column(Integer, default=2)  # 1 or 2
    state = Column(String(100))
    employee_count = Column(Integer, default=1)
    num_sites = Column(Integer, default=1)
    annual_turnover_band = Column(String(100))
    has_gstin = Column(Boolean, default=False)
    gstin = Column(String(20))
    has_udyam = Column(Boolean, default=False)
    udyam_number = Column(String(30))
    current_internet = Column(String(100))
    monthly_telecom_spend_inr = Column(Float)
    preferred_language = Column(String(50), default="English")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="business")
    conversations = relationship("Conversation", back_populates="business")
    quotes = relationship("Quote", back_populates="business")
    kyc_records = relationship("KYCRecord", back_populates="business")
    consent_records = relationship("ConsentRecord", back_populates="business")


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    session_id = Column(String(100), unique=True, index=True)
    language = Column(String(50), default="English")
    messages_json = Column(Text, default="[]")  # JSON array of {role, content, timestamp}
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business = relationship("Business", back_populates="conversations")

    @property
    def messages(self):
        return json.loads(self.messages_json)

    @messages.setter
    def messages(self, value):
        self.messages_json = json.dumps(value)


class Quote(Base):
    __tablename__ = "quotes"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    line_items_json = Column(Text, default="[]")  # [{product_id, qty, unit_price, setup_fee}]
    total_monthly_inr = Column(Float, default=0)
    total_setup_inr = Column(Float, default=0)
    contract_months = Column(Integer, default=12)
    status = Column(String(20), default="DRAFT")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business = relationship("Business", back_populates="quotes")
    order = relationship("Order", back_populates="quote", uselist=False)

    @property
    def line_items(self):
        return json.loads(self.line_items_json)

    @line_items.setter
    def line_items(self, value):
        self.line_items_json = json.dumps(value)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    status = Column(String(50), default=OrderStatus.ORDER_CONFIRMED.value)
    typical_install_days = Column(Integer, default=7)
    timeline_json = Column(Text, default="[]")  # [{status, timestamp, note}]
    created_at = Column(DateTime, default=datetime.utcnow)

    quote = relationship("Quote", back_populates="order")

    @property
    def timeline(self):
        return json.loads(self.timeline_json)

    @timeline.setter
    def timeline(self, value):
        self.timeline_json = json.dumps(value)


class KYCRecord(Base):
    __tablename__ = "kyc_records"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    gstin_verified = Column(String(20), default="PENDING")  # PENDING|VERIFIED|FAILED
    udyam_verified = Column(String(20), default="PENDING")
    gst_cert_status = Column(String(20), default="PENDING")
    udyam_cert_status = Column(String(20), default="PENDING")
    signatory_id_status = Column(String(20), default="PENDING")
    address_proof_status = Column(String(20), default="PENDING")
    overall_status = Column(String(20), default="PENDING")
    ocr_data_json = Column(Text, default="{}")  # extracted OCR fields
    failure_reasons_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    business = relationship("Business", back_populates="kyc_records")

    @property
    def ocr_data(self):
        return json.loads(self.ocr_data_json)

    @property
    def failure_reasons(self):
        return json.loads(self.failure_reasons_json)


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    purpose = Column(String(200), nullable=False)  # e.g. "KYC document collection"
    consented = Column(Boolean, default=False)
    consent_text = Column(Text)  # exact text shown at time of consent
    ip_address = Column(String(50))
    consented_at = Column(DateTime, default=datetime.utcnow)
    withdrawn_at = Column(DateTime, nullable=True)

    business = relationship("Business", back_populates="consent_records")


class Lead(Base):
    """Mirror of smb_leads.csv loaded at startup. Read-only from app perspective."""
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(String(20), unique=True, index=True)
    created_date = Column(Date)
    lead_source = Column(String(100))
    business_name = Column(String(255))
    business_type = Column(String(100))
    segment = Column(String(50))
    city = Column(String(100))
    city_tier = Column(Integer)
    state = Column(String(100))
    preferred_language = Column(String(50))
    employee_count = Column(Integer)
    num_sites = Column(Integer)
    annual_turnover_band = Column(String(100))
    has_gstin = Column(Boolean)
    gstin = Column(String(20))
    has_udyam = Column(Boolean)
    udyam_number = Column(String(30))
    current_internet = Column(String(100))
    current_provider = Column(String(100))
    monthly_telecom_spend_inr = Column(Float)
    products_of_interest = Column(String(200))
    contact_name = Column(String(200))
    contact_role = Column(String(100))
    stage_reached = Column(String(100))
    outcome = Column(String(50))
    drop_reason = Column(String(200))
    contacted_date = Column(Date, nullable=True)
    needs_assessed_date = Column(Date, nullable=True)
    quote_accepted_date = Column(Date, nullable=True)
    kyc_complete_date = Column(Date, nullable=True)
    activated_date = Column(Date, nullable=True)
    days_lead_to_activation = Column(Float, nullable=True)
    customer_follow_up_calls = Column(Float, nullable=True)
    bundle_products = Column(String(200))
    monthly_bundle_value_inr = Column(Float, nullable=True)
    one_time_setup_inr = Column(Float, nullable=True)
    contract_months = Column(Float, nullable=True)
    churned_within_6_months = Column(String(5))
    nps_score = Column(Float, nullable=True)
    acquisition_cost_inr = Column(Float, nullable=True)
    # Recovery score (computed at load time)
    recovery_score = Column(Float, default=0)

    assignments = relationship("PartnerAssignment", back_populates="lead")


class ChannelPartner(Base):
    __tablename__ = "channel_partners"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=False)
    region = Column(String(100))
    city = Column(String(100))
    tier = Column(Integer, default=2)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="partner")
    assignments = relationship("PartnerAssignment", back_populates="partner")


class PartnerAssignment(Base):
    __tablename__ = "partner_assignments"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    partner_id = Column(Integer, ForeignKey("channel_partners.id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="Assigned")  # Assigned|In Progress|Closed
    commission_inr = Column(Float, default=0)
    notes = Column(Text)

    lead = relationship("Lead", back_populates="assignments")
    partner = relationship("ChannelPartner", back_populates="assignments")
