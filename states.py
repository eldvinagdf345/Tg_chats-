from aiogram.fsm.state import State, StatesGroup


class AccountStates(StatesGroup):
    waiting_label          = State()
    waiting_api_id         = State()
    waiting_api_hash       = State()
    waiting_session_string = State()
    waiting_phone          = State()
    waiting_phone_code     = State()
    waiting_2fa_password   = State()


class InstructionsChatStates(StatesGroup):
    """Free-form chat where the account owner describes, in their own words,
    how the assistant should behave — replaces the old fixed questionnaire."""
    chatting = State()


class QuickSettingStates(StatesGroup):
    """Generic single-value editor for one hard-rule/timing setting at a
    time (stop-words, message limits, work hours, notify chat, delays...).
    Which setting is being edited is kept in FSM data under 'setting_key'."""
    waiting_value = State()


class DialogueSetupStates(StatesGroup):
    waiting_contact         = State()
    waiting_goal            = State()
    waiting_opening_message = State()


class DraftEditStates(StatesGroup):
    waiting_new_text = State()


class DialogueBulkStates(StatesGroup):
    """Multi-select mode in the dialogues list for annulling several
    contacts at once. Selected ids are kept in FSM data under 'selected_ids'."""
    selecting = State()


class TemplateStates(StatesGroup):
    waiting_name = State()


class AccountLinkStates(StatesGroup):
    """Multi-select mode for linking several accounts into one group that
    shares (and keeps in sync) a single instructions document."""
    selecting = State()


class BaseAssignStates(StatesGroup):
    """Assigning specific base contacts to one chosen account — the account
    id is kept in FSM data under 'assign_account_id'."""
    waiting_contacts = State()
