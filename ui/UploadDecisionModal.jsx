import React from 'react';
import { useAppState } from './context/AppStateContext.jsx';
import { useWorkspace } from './context/WorkspaceContext.jsx';

export default function UploadDecisionModal() {
    const { uploadDecisionFlow, setUploadDecisionFlow, setActiveView } = useAppState();
    const { createWorkspace, selectWorkspace } = useWorkspace();

    if (!uploadDecisionFlow || uploadDecisionFlow.step === 0) return null;

    const { files, step } = uploadDecisionFlow;
    if (!files || files.length === 0) return null;

    const handleClose = () => {
        setUploadDecisionFlow(prev => ({ ...prev, step: 0, files: [] }));
    };

    const handleStep1Append = () => {
        setUploadDecisionFlow(prev => ({ ...prev, step: 2, mode: 'append' }));
    };

    const handleStep1NewWorkspace = () => {
        const newId = createWorkspace(files[0]?.name || '새 작업');
        selectWorkspace(newId);
        setActiveView('workspace');

        setUploadDecisionFlow(prev => ({
            ...prev,
            step: 0,
            targetWorkspaceId: newId,
            mode: 'new-workspace',
            integration: 'regenerate-proposals'
        }));
    };

    const handleStep2SourceOnly = () => {
        setUploadDecisionFlow(prev => ({
            ...prev,
            step: 0,
            integration: 'source-only'
        }));
    };

    const handleStep2Regenerate = () => {
        setUploadDecisionFlow(prev => ({
            ...prev,
            step: 0,
            integration: 'regenerate-proposals'
        }));
    };

    const overlayStyle = {
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.7)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999
    };

    const modalStyle = {
        background: '#18181b', border: '1px solid #27272a', borderRadius: '12px',
        padding: '32px', width: '400px', maxWidth: '90vw', color: '#eaeaeb',
        fontFamily: 'sans-serif', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)'
    };

    const btnGrp = { display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '24px' };

    const btnStyle = {
        background: '#27272a', border: '1px solid #3f3f46', borderRadius: '6px',
        padding: '14px 16px', color: '#eaeaeb', fontSize: '14px', cursor: 'pointer',
        transition: 'all 0.15s ease', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: '4px'
    };

    return (
        <div style={overlayStyle} onClick={handleClose}>
            <div style={modalStyle} onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <div style={{ fontSize: '13px', color: '#a1a1aa' }}>업로드 옵션 선택</div>
                    <button onClick={handleClose} style={{ background: 'transparent', border: 'none', color: '#71717a', cursor: 'pointer', fontSize: '18px' }}>×</button>
                </div>

                <h2 style={{ margin: '0 0 20px 0', fontSize: '18px', fontWeight: 500, lineHeight: 1.4 }}>
                    {step === 1 ? `선택한 영상(${files.length}개)을 어디에 넣을까요?` : '어떻게 반영할까요?'}
                </h2>

                <div style={btnGrp}>
                    {step === 1 ? (
                        <>
                            <button style={btnStyle} onClick={handleStep1Append} onMouseOver={e => e.currentTarget.style.borderColor = '#38bdf8'} onMouseOut={e => e.currentTarget.style.borderColor = '#3f3f46'}>
                                <span style={{ fontWeight: 500 }}>현재 작업에 추가</span>
                                <span style={{ fontSize: '12px', color: '#a1a1aa' }}>새 줄을 생성해 영상을 병합합니다.</span>
                            </button>
                            <button style={btnStyle} onClick={handleStep1NewWorkspace} onMouseOver={e => e.currentTarget.style.borderColor = '#38bdf8'} onMouseOut={e => e.currentTarget.style.borderColor = '#3f3f46'}>
                                <span style={{ fontWeight: 500 }}>새 작업으로 시작</span>
                                <span style={{ fontSize: '12px', color: '#a1a1aa' }}>기존 편집은 보존하고 새 탭을 엽니다.</span>
                            </button>
                        </>
                    ) : (
                        <>
                            <button style={{ ...btnStyle, borderColor: '#10b981' }} onClick={handleStep2SourceOnly}>
                                <span style={{ fontWeight: 500, color: '#10b981' }}>원본만 추가하고 직접 편집</span>
                                <span style={{ fontSize: '12px', color: '#a1a1aa' }}>기존 편집 상태를 그대로 유지합니다.</span>
                            </button>
                            <button style={btnStyle} onClick={handleStep2Regenerate} onMouseOver={e => e.currentTarget.style.borderColor = '#38bdf8'} onMouseOut={e => e.currentTarget.style.borderColor = '#3f3f46'}>
                                <span style={{ fontWeight: 500 }}>제안 2개 다시 받기</span>
                                <span style={{ fontSize: '12px', color: '#a1a1aa' }}>모든 영상을 다시 섞어 새로운 시안을 확인합니다. (기존 편집은 덮어쓰지 않습니다)</span>
                            </button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
