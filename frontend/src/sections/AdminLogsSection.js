// src/sections/AdminLogsSection.jsx
import React, { useState, useEffect, useContext } from 'react';
import styled from 'styled-components';
import AuthContext from '../context/AuthContext';
import { motion } from 'framer-motion';
import { FaUser, FaClock, FaInfoCircle, FaPlusCircle, FaEdit, FaTimesCircle, FaTruck } from 'react-icons/fa';

const getLogStyles = (actionText) => {
  const text = actionText.toLowerCase();
  if (text.includes('cancel') || text.includes('delete') || text.includes('removed')) return { color: '#EF4444', icon: <FaTimesCircle /> }; 
  if (text.includes('shipped') || text.includes('delivered')) return { color: '#3B82F6', icon: <FaTruck /> }; 
  if (text.includes('update') || text.includes('renamed') || text.includes('status:')) return { color: '#F59E0B', icon: <FaEdit /> }; 
  if (text.includes('create') || text.includes('add') || text.includes('new order')) return { color: '#10B981', icon: <FaPlusCircle /> }; 
  return { color: '#64748B', icon: <FaInfoCircle /> };
};

const AdminLogsSection = () => {
  const { axiosInstance } = useContext(AuthContext);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  // Pagination State
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const res = await axiosInstance.get(`/api/admin-logs/?page=${currentPage}`);
        setLogs(res.data.results || res.data);
        if (res.data.count) setTotalPages(Math.ceil(res.data.count / 12));
      } catch (err) { console.error("Error fetching logs", err); } 
      finally { setLoading(false); }
    };
    fetchLogs();
  }, [axiosInstance, currentPage]);

  return (
    <LogContainer>
      <SectionHeading>🔐 System Audit Logs</SectionHeading>
      {loading ? (
        <LoadingWrapper><Spinner /><LoadingText>Loading audit logs...</LoadingText></LoadingWrapper>
      ) : logs.length === 0 ? (
        <EmptyState><span className="emoji">📝</span><h3>No logs found</h3><p>There are no recorded system activities yet.</p></EmptyState>
      ) : (
        logs.map((log) => {
          const { color, icon } = getLogStyles(log.action);
          return (
            <LogItem key={log.id} $borderColor={color} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} whileHover={{ x: 4 }}>
              <LogHeader>
                <span className="user"><FaUser /> {log.admin?.username || 'System'}</span>
                <span className="time"><FaClock /> {new Date(log.timestamp).toLocaleString()}</span>
              </LogHeader>
              <LogBody $iconColor={color}>
                <span className="icon-wrapper">{icon}</span> <span className="text">{log.action}</span>
              </LogBody>
            </LogItem>
          );
        })
      )}

      {totalPages > 1 && (
        <PaginationWrapper>
          <PageButton onClick={() => setCurrentPage(p => Math.max(p - 1, 1))} disabled={currentPage === 1}>&larr; Prev</PageButton>
          <PageInfo>Page {currentPage} of {totalPages}</PageInfo>
          <PageButton onClick={() => setCurrentPage(p => Math.min(p + 1, totalPages))} disabled={currentPage === totalPages}>Next &rarr;</PageButton>
        </PaginationWrapper>
      )}
    </LogContainer>
  );
};

export default AdminLogsSection;

// STYLED COMPONENTS
const LogContainer = styled.div` display: flex; flex-direction: column; gap: 1rem; `;
const SectionHeading = styled.h2` color: #0F172A; margin-bottom: 0.5rem; font-size: 1.5rem; font-weight: 800; `;

const LoadingWrapper = styled.div` display: flex; flex-direction: column; align-items: center; justify-content: center; margin-top: 4rem; `;
const Spinner = styled.div` width: 45px; height: 45px; border: 4px solid #E2E8F0; border-top: 4px solid #0B8457; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 1rem; @keyframes spin { to { transform: rotate(360deg); } } `;
const LoadingText = styled.div` font-size: 1.1rem; font-weight: 600; color: #0B8457; `;

const EmptyState = styled.div`
  text-align: center; padding: 5rem 2rem; background: #ffffff; border-radius: 24px; border: 1px dashed #CBD5E1;
  .emoji { font-size: 3.5rem; display: block; margin-bottom: 1rem; }
  h3 { color: #0F172A; font-size: 1.5rem; font-weight: 800; margin-bottom: 0.5rem; }
  p { color: #64748B; font-size: 1rem; }
`;

const LogItem = styled(motion.div)` 
  background: #ffffff; padding: 1.5rem; border-radius: 20px; border-left: 6px solid ${props => props.$borderColor}; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border-top: 1px solid rgba(11, 132, 87, 0.08); border-right: 1px solid rgba(11, 132, 87, 0.08); border-bottom: 1px solid rgba(11, 132, 87, 0.08); transition: transform 0.2s ease; 
`;

const LogHeader = styled.div` 
  display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; margin-bottom: 0.8rem; 
  .user { font-weight: 700; color: #0F172A; display: flex; align-items: center; gap: 0.5rem; font-size: 0.95rem; } 
  .time { display: flex; align-items: center; gap: 0.4rem; color: #64748B; font-weight: 600; background-color: #F8FAFC; padding: 0.3rem 0.8rem; border-radius: 20px; border: 1px solid #E2E8F0; } 
`;

const LogBody = styled.div` 
  display: flex; align-items: flex-start; gap: 0.8rem; color: #334155; font-weight: 500; line-height: 1.5; 
  .icon-wrapper { color: ${props => props.$iconColor}; font-size: 1.2rem; display: flex; margin-top: 2px; } 
  .text { flex: 1; font-size: 1rem; } 
`;

const PaginationWrapper = styled.div` display: flex; justify-content: center; align-items: center; gap: 1rem; margin-top: 3rem; padding-bottom: 1rem; `;
const PageButton = styled.button` padding: 0.6rem 1.4rem; border-radius: 50px; border: none; font-weight: 700; background: ${props => props.disabled ? '#F1F5F9' : '#0B8457'}; color: ${props => props.disabled ? '#94A3B8' : 'white'}; cursor: ${props => props.disabled ? 'not-allowed' : 'pointer'}; transition: 0.2s; box-shadow: ${props => props.disabled ? 'none' : '0 4px 10px rgba(11, 132, 87, 0.2)'}; &:hover:not(:disabled) { background: #086341; transform: translateY(-1px); } `;
const PageInfo = styled.span` font-weight: 700; color: #334155; font-size: 0.95rem; background: #ffffff; padding: 0.6rem 1.2rem; border-radius: 50px; border: 1px solid #E2E8F0; `;