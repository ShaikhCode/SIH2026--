import secrets
import string
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...db import get_db
from ...models import Group, Membership, User, Lesson
from ...schemas import GroupIn, JoinIn
from ...core.security import current_user, require_admin

router = APIRouter(prefix='/groups', tags=['groups'])

def make_code() -> str:
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(7))

def group_view(db: Session, g: Group) -> dict:
    return {
        'id': g.id, 'name': g.name, 'join_code': g.join_code, 'grade': g.grade,
        'subject': g.subject, 'owner_id': g.owner_id,
        'members': db.query(Membership).filter_by(group_id=g.id).count(),
        'lessons': db.query(Lesson).filter_by(group_id=g.id).count(),
        'created_at': g.created_at.isoformat(),
    }

@router.post('')
def create_group(x: GroupIn, db: Session = Depends(get_db), u=Depends(require_admin)):
    join = make_code()
    while db.query(Group).filter_by(join_code=join).first():
        join = make_code()
    g = Group(name=x.name.strip(), grade=x.grade.strip(), subject=x.subject.strip(), join_code=join, owner_id=u.id)
    db.add(g); db.flush()
    db.add(Membership(group_id=g.id, user_id=u.id, role='admin'))
    db.commit(); db.refresh(g)
    return group_view(db, g)

@router.get('')
def list_groups(db: Session = Depends(get_db), u=Depends(current_user)):
    if u.account_role == 'admin':
        rows = db.query(Group).filter_by(owner_id=u.id).order_by(Group.id.desc()).all()
    else:
        ids = [m.group_id for m in db.query(Membership).filter_by(user_id=u.id).all()]
        rows = db.query(Group).filter(Group.id.in_(ids or [-1])).order_by(Group.id.desc()).all()
    return [group_view(db, g) for g in rows]

@router.get('/{group_id}')
def get_group(group_id: int, db: Session = Depends(get_db), u=Depends(current_user)):
    g = db.get(Group, group_id)
    if not g:
        raise HTTPException(404, detail={'code':'GROUP_NOT_FOUND','message':'Group not found.'})
    allowed = g.owner_id == u.id or bool(db.query(Membership).filter_by(group_id=g.id, user_id=u.id).first())
    if not allowed:
        raise HTTPException(403, detail={'code':'GROUP_ACCESS_DENIED','message':'You are not a member of this group.'})
    return group_view(db, g)

@router.post('/join')
def join_group(x: JoinIn, db: Session = Depends(get_db), u=Depends(current_user)):
    g = db.query(Group).filter_by(join_code=x.join_code.strip().upper()).first()
    if not g:
        raise HTTPException(404, detail={'code':'JOIN_CODE_INVALID','message':'That join code is not valid.'})
    existing = db.query(Membership).filter_by(group_id=g.id, user_id=u.id).first()
    if existing:
        return {'already_member': True, 'group': group_view(db, g)}
    db.add(Membership(group_id=g.id, user_id=u.id, role='student'))
    db.commit()
    return {'already_member': False, 'group': group_view(db, g)}

@router.get('/{group_id}/members')
def members(group_id: int, db: Session = Depends(get_db), u=Depends(current_user)):
    g = db.get(Group, group_id)
    if not g:
        raise HTTPException(404, detail={'code':'GROUP_NOT_FOUND','message':'Group not found.'})
    if g.owner_id != u.id and u.account_role != 'admin':
        raise HTTPException(403, detail={'code':'ADMIN_REQUIRED','message':'Administrator access is required.'})
    rows = db.query(Membership, User).join(User, User.id == Membership.user_id).filter(Membership.group_id == group_id).all()
    return [
        {'id': m.id, 'user_id': user.id, 'name': user.name, 'email': user.email, 'role': m.role, 'joined_at': m.joined_at.isoformat()}
        for m, user in rows
    ]
