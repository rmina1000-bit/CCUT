import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useLayout } from '../context/LayoutContext';
import { useVideo } from '../context/VideoContext';
import ResizablePanel from './ResizablePanel.jsx';
import ResizeHandle from './ResizeHandle.jsx';
import LeftPanel from '../left_panel.jsx';
import CenterPanel from '../center_panel.jsx';
import RightPanel from '../right_panel.jsx';

export default function MainLayout({ fragments = [], onFragments, onAction, onFragmentsLoad }) {
  const { widths, collapsed, setRef } = useLayout();
  const { setVideoURL, videoURL } = useVideo();
  const containerRef = useRef(null);

  useEffect(() => {
    setRef('container', containerRef.current);
  }, [setRef]);

  const [messages, setMessages] = useState([
    { role: 'system', text: '영상을 드래그 앤 드롭으로 올리세요.' },
  ]);
  const [input, setInput] = useState('');
  const [proposals, setProposals] = useState([]);
  const [isEditing, setIsEditing] = useState(false);
  const [selectedProposal, setSelectedProposal] = useState(null);

  const handleFileUpload = useCallback((file) => {
    const url = URL.createObjectURL(file);
    setVideoURL(url);

    // Mock fragments generation out of thin air to simulate AI proposal engine
    const MOCK_FRAGMENTS = Array.from({ length: 8 }).map((_, i) => ({
      id: i + 1,
      start: i * 3,
      end: i * 3 + 3,
      duration: 3
    }));
    onFragmentsLoad?.(MOCK_FRAGMENTS);

    const userMsg = { role: 'user', text: `Uploaded Video: ${file.name}` };
    setMessages(prev => [...prev, userMsg, { role: 'system', text: '영상 분석을 시작합니다. 잠시만 기다려주세요...' }]);

    // Simulate Fake AI Engine processing
    setTimeout(() => {
      setMessages(prev => [...prev, { role: 'system', text: '분석 완료! 2개의 제안(Proposal)이 우측에 생성되었습니다. (1 또는 2를 선택)' }]);
      setProposals([
        { id: 'A', title: 'Proposal A', description: 'Fast cut, high energy', fragments: [1, 3] },
        { id: 'B', title: 'Proposal B', description: 'Smooth transition, narrative', fragments: [2, 4] }
      ]);
    }, 1500);
  }, [setVideoURL, onFragmentsLoad]);

  const handleSelectProposal = useCallback((p) => {
    setProposals([]);
    setSelectedProposal(p);
    setIsEditing(true);
    setMessages(prev => [...prev, { role: 'system', text: `${p.id}를 선택하셨습니다. 편집으로 넘어갑니다.` }]);
  }, []);

  const handleSend = useCallback(() => {
    if (!input.trim()) return;
    const userMsg = { role: 'user', text: input };
    setMessages(prev => [...prev, userMsg]);
    onAction?.(input);

    const lower = input.toLowerCase().trim();
    let reply = `Command received: ${input}`;

    // Check if user wants new proposals
    if (lower.includes('다른 영상') || lower.includes('다시 제안') || lower === 'reject') {
      reply = '새로운 제안을 분석 중입니다... 잠시만 기다려주세요.';
      setMessages(prev => [...prev, { role: 'system', text: reply }]);
      setInput('');

      // Clear current editing status to show proposals again
      setIsEditing(false);
      setProposals([]);

      setTimeout(() => {
        setMessages(prev => [...prev, { role: 'system', text: '새로운 분석 완료! 제안 C와 D가 생성되었습니다.' }]);
        setProposals([
          { id: 'C', title: 'Proposal C', description: 'Cinematic look, slow pace', fragments: [1, 2, 5] },
          { id: 'D', title: 'Proposal D', description: 'Action-packed, dynamic', fragments: [3, 4, 6] }
        ]);
      }, 1500);
      return;
    }

    if (['1', 'a', 'first'].includes(lower)) {
      reply = 'Selected Proposal A.';
      if (proposals.length > 0) {
        setSelectedProposal(proposals[0]);
        setProposals([]);
        setIsEditing(true);
      }
    }
    else if (['2', 'b', 'second'].includes(lower)) {
      reply = 'Selected Proposal B.';
      if (proposals.length > 1) {
        setSelectedProposal(proposals[1]);
        setProposals([]);
        setIsEditing(true);
      }
    }
    else if (['c'].includes(lower)) {
      reply = 'Selected Proposal C.';
      if (proposals.length > 0) {
        setSelectedProposal(proposals[0]);
        setProposals([]);
        setIsEditing(true);
      }
    }
    else if (['d'].includes(lower)) {
      reply = 'Selected Proposal D.';
      if (proposals.length > 1) {
        setSelectedProposal(proposals[1]);
        setProposals([]);
        setIsEditing(true);
      }
    }
    else if (lower === 'play') reply = 'Preview playback started.';

    setMessages(prev => [...prev, { role: 'system', text: reply }]);
    setInput('');
  }, [input, onAction, proposals]);

  const chatProps = {
    messages,
    input,
    setInput,
    onSend: handleSend,
    disabled: false,
    onFileUpload: handleFileUpload,
    proposals,
    onSelectProposal: handleSelectProposal,
    videoURL
  };

  // Determine if Chat should move to Right Panel
  // Criteria: Center width < 25 or is collapsed
  const isChatMoved = widths.center < 25 || collapsed.center;

  return (
    <div ref={containerRef} className="main-layout" id="main-layout" style={{
      display: 'flex',
      width: '100%',
      height: '100vh',
      background: '#0d1117',
      overflow: 'hidden'
    }}>
      <ResizablePanel id="left">
        <LeftPanel isEditing={isEditing} onWorkspaceCreate={() => { }} onWorkspaceSelect={() => { }} onFragmentsLoad={onFragmentsLoad} />
      </ResizablePanel>

      <ResizeHandle between="lc" />

      <ResizablePanel id="center">
        <CenterPanel
          chatProps={{ ...chatProps, renderMode: isChatMoved ? 'messages' : 'all' }}
          addMessage={(msg) => setMessages(prev => [...prev, msg])}
        />
      </ResizablePanel>

      <ResizeHandle between="cr" />

      <ResizablePanel id="right">
        <RightPanel
          isEditing={isEditing}
          selectedProposal={selectedProposal}
          fragments={fragments}
          onFragmentsChange={onFragments}
          chatProps={isChatMoved ? { ...chatProps, renderMode: 'input' } : null}
        />
      </ResizablePanel>
    </div>
  );
}
