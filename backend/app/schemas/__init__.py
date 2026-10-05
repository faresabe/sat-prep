from app.schemas.auth import (
    RefreshRequest,
    TokenResponse,
    UserLogin,
    UserSignup,
)
from app.schemas.user import UserAdminRead, UserRead, UserUpdate
from app.schemas.content import (
    ChoiceCreate,
    ChoiceRead,
    DomainRead,
    PassageRead,
    QuestionAdminRead,
    QuestionCreate,
    QuestionRead,
    SkillRead,
)
from app.schemas.test import (
    ModuleQuestionRead,
    TestDetail,
    TestModuleDetail,
    TestModuleRead,
    TestRead,
    TestSectionRead,
)
from app.schemas.attempt import (
    AnswerRead,
    AttemptDetail,
    AttemptRead,
    ModuleAttemptRead,
    ModuleServeResponse,
    SaveAnswerRequest,
    StartAttemptRequest,
    StartModuleRequest,
    SubmitModuleRequest,
)
from app.schemas.result import (
    DomainResultRead,
    ScoreReportDetail,
    ScoreReportRead,
    SkillResultRead,
)
from app.schemas.stats import (
    UserDomainStatRead,
    UserSkillStatRead,
    UserStatRead,
    WeaknessReport,
)

__all__ = [
    # auth
    "UserSignup", "UserLogin", "RefreshRequest", "TokenResponse",
    # user
    "UserRead", "UserUpdate", "UserAdminRead",
    # content
    "DomainRead", "SkillRead", "PassageRead",
    "ChoiceRead", "ChoiceCreate",
    "QuestionRead", "QuestionAdminRead", "QuestionCreate",
    # test
    "TestRead", "TestDetail",
    "TestSectionRead",
    "TestModuleRead", "TestModuleDetail",
    "ModuleQuestionRead",
    # attempt
    "StartAttemptRequest", "StartModuleRequest",
    "SaveAnswerRequest", "SubmitModuleRequest",
    "AnswerRead", "ModuleAttemptRead",
    "AttemptRead", "AttemptDetail", "ModuleServeResponse",
    # result
    "ScoreReportRead", "ScoreReportDetail",
    "DomainResultRead", "SkillResultRead",
    # stats
    "UserStatRead", "UserSkillStatRead", "UserDomainStatRead",
    "WeaknessReport",
]