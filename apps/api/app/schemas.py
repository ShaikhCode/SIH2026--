from typing import Any, Literal
from pydantic import BaseModel,Field
LanguageCode=Literal['eng_Latn','hin_Deva','sat_Olck']
class RegisterIn(BaseModel): name:str=Field(min_length=2,max_length=120); email:str=Field(min_length=5,max_length=255); password:str=Field(min_length=8,max_length=128); preferred_language:LanguageCode='hin_Deva'; account_role:Literal['student','admin']='student'
class LoginIn(BaseModel): email:str=Field(min_length=5,max_length=255); password:str
class GroupIn(BaseModel): name:str=Field(min_length=2,max_length=160); grade:str=Field(default='Grade 2',max_length=50); subject:str=Field(default='Environmental Studies',max_length=100)
class JoinIn(BaseModel): join_code:str=Field(min_length=4,max_length=32)
class LessonCreateIn(BaseModel): title:str=Field(min_length=2,max_length=200); source_text:str=''; source_language:LanguageCode='hin_Deva'; grade:str='Grade 2'; subject:str='Environmental Studies'; topic:str=''
class LessonPatchIn(BaseModel): title:str|None=None; source_text:str|None=None; clean_transcript:str|None=None; topic:str|None=None; learning_outcome:str|None=None; concepts:list[str]|None=None
class VersionCreateIn(BaseModel): source_text:str|None=None; clean_transcript:str|None=None; learning_outcome:str|None=None; concepts:list[str]|None=None
class TranslateIn(BaseModel): target_language:LanguageCode
class VerifyIn(BaseModel): translation_id:int; approved:bool; edited_text:str|None=None; native_review_status:Literal['NOT_REVIEWED','PENDING','VERIFIED','REJECTED']|None=None
class PracticeGenerateIn(BaseModel): language:LanguageCode='hin_Deva'; count:int=Field(default=4,ge=1,le=10)
class AttemptIn(BaseModel): answers:dict[str,Any]; lesson_version_id:int|None=None; offline_created_at:str|None=None
class SyncPushIn(BaseModel): device_id:str; operations:list[dict[str,Any]]=Field(default_factory=list)
class TTSIn(BaseModel): target_language:LanguageCode='sat_Olck'; speaker:str='classroom_teacher'
class FlashcardIn(BaseModel): language:LanguageCode='hin_Deva'
