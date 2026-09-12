from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership, MemberRole

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str
    description: Optional[str] = None


class WorkspaceOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    role: str


def _membership_or_404(db: Session, user_id, workspace_id) -> WorkspaceMembership:
    m = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return m


@router.post("", response_model=WorkspaceOut, status_code=201)
def create_workspace(
    req: CreateWorkspaceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = Workspace(name=req.name, description=req.description)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMembership(
        user_id=current_user.id,
        workspace_id=ws.id,
        role=MemberRole.owner,
    ))
    db.commit()
    db.refresh(ws)
    return WorkspaceOut(id=str(ws.id), name=ws.name, description=ws.description, role="owner")


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    memberships = (
        db.query(WorkspaceMembership)
        .filter(WorkspaceMembership.user_id == current_user.id)
        .all()
    )
    return [
        WorkspaceOut(
            id=str(m.workspace.id),
            name=m.workspace.name,
            description=m.workspace.description,
            role=m.role.value,
        )
        for m in memberships
    ]


@router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = _membership_or_404(db, current_user.id, workspace_id)
    ws = m.workspace
    return WorkspaceOut(id=str(ws.id), name=ws.name, description=ws.description, role=m.role.value)
