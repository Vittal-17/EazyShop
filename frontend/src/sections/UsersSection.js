// src/sections/UsersSection.jsx
import { useState, useEffect, useContext } from 'react';
import styled from 'styled-components';
import { motion, AnimatePresence } from 'framer-motion';
import AuthContext from '../context/AuthContext';
import { toast } from "react-hot-toast";
import { FaTimes, FaUser, FaUserShield, FaTrash, FaEdit, FaStore } from 'react-icons/fa';
import ModalPortal from '../components/ModalPortal';

const UsersSection = () => {
  const { axiosInstance } = useContext(AuthContext);
  const [users, setUsers] = useState([]);
  const [activeUser, setActiveUser] = useState(null); 
  
  // Pagination State
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [userToDelete, setUserToDelete] = useState(null);

  const fetchUsers = async () => {
    try {
      const res = await axiosInstance.get(`/api/users/?page=${currentPage}`);
      setUsers(res.data.results || res.data);
      if (res.data.count) setTotalPages(Math.ceil(res.data.count / 12));
    } catch { setUsers([]); }
  };

  useEffect(() => {
    fetchUsers();
    // eslint-disable-next-line
  }, [axiosInstance, currentPage]);

  const executeDelete = async () => {
    if (!userToDelete) return;
    try {
      await axiosInstance.delete(`/api/users/${userToDelete}/`);
      toast.success('🗑️ User deleted');
      fetchUsers();
    } catch { toast.error('❌ Failed to delete user'); } 
    finally { setIsDeleteModalOpen(false); setUserToDelete(null); }
  };

  const handleRoleChange = async (id, role) => {
    try {
      await axiosInstance.patch(`/api/users/${id}/`, { role });
      toast.success(`✅ Role updated to ${role.toUpperCase()}`);
      setActiveUser(null);
      fetchUsers();
    } catch { toast.error('❌ Failed to update role'); }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <SectionTitle>👥 Manage Users</SectionTitle>
      <ul style={{ padding: 0, listStyle: 'none' }}>
        {users.map(u => (
          <ListItem key={u.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} whileHover={{ y: -2 }}>
            <div>
              <div style={{ fontSize: '1.15rem', fontWeight: '800', color: '#0F172A' }}>{u.username}</div>
              <div style={{ color: '#64748B', fontSize: '0.95netrem', marginTop: '0.2rem', fontWeight: '500' }}>{u.email}</div>
            </div>
            <ControlsWrapper>
              <RoleTriggerButton 
                $role={u.role} 
                onClick={() => setActiveUser(u)} 
                whileHover={{ scale: 1.02 }} 
                whileTap={{ scale: 0.98 }}
              >
                {u.role === 'admin' ? <FaUserShield /> : u.role === 'seller' ? <FaStore /> : <FaUser />} 
                {u.role} 
                <FaEdit style={{ marginLeft: '4px' }} />
              </RoleTriggerButton>
              <DeleteButton onClick={() => { setUserToDelete(u.id); setIsDeleteModalOpen(true); }} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                <FaTrash /> Delete
              </DeleteButton>
            </ControlsWrapper>
          </ListItem>
        ))}
      </ul>

      {totalPages > 1 && (
        <PaginationWrapper>
          <PageButton onClick={() => setCurrentPage(p => Math.max(p - 1, 1))} disabled={currentPage === 1}>&larr; Prev</PageButton>
          <PageInfo>Page {currentPage} of {totalPages}</PageInfo>
          <PageButton onClick={() => setCurrentPage(p => Math.min(p + 1, totalPages))} disabled={currentPage === totalPages}>Next &rarr;</PageButton>
        </PaginationWrapper>
      )}

      {/* Modals */}
      <AnimatePresence>
        {isDeleteModalOpen && (
          <ModalPortal>
          <ConfirmOverlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <ConfirmCard initial={{ scale: 0.9, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.9, opacity: 0, y: 10 }}>
              <h3>Delete User</h3>
              <p>Delete this user profile entirely? They will lose all access.</p>
              <ButtonGroup>
                <CancelBtn onClick={() => setIsDeleteModalOpen(false)}>Cancel</CancelBtn>
                <ConfirmDeleteBtn onClick={executeDelete}>Yes, Delete</ConfirmDeleteBtn>
              </ButtonGroup>
            </ConfirmCard>
          </ConfirmOverlay>
          </ModalPortal>
        )}
        {activeUser && (
          <ModalPortal>
          <ModalOverlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setActiveUser(null)}>
            <ModalCard initial={{ scale: 0.9, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.9, opacity: 0, y: 10 }} onClick={e => e.stopPropagation()}>
              <CloseButton onClick={() => setActiveUser(null)}><FaTimes /></CloseButton>
              <h3 style={{ margin: '0 0 1.5rem 0', color: '#0F172A', textAlign: 'center', fontWeight: '800' }}>Set Role for {activeUser.username}</h3>
              
              <StatusOptionBtn $bg="#ECFDF5" $fg="#047857" $borderColor="#10B981" $active={activeUser.role === 'user'} onClick={() => handleRoleChange(activeUser.id, 'user')} whileHover={{ scale: 1.02 }}>
                <FaUser /> <span style={{ flex: 1, textAlign: 'left' }}>Standard User</span> {activeUser.role === 'user' && <span style={{ fontSize: '0.8rem', opacity: 0.7 }}>(Current)</span>}
              </StatusOptionBtn>
              
              <StatusOptionBtn $bg="#DBEAFE" $fg="#1D4ED8" $borderColor="#3B82F6" $active={activeUser.role === 'seller'} onClick={() => handleRoleChange(activeUser.id, 'seller')} whileHover={{ scale: 1.02 }}>
                <FaStore /> <span style={{ flex: 1, textAlign: 'left' }}>Vendor / Seller</span> {activeUser.role === 'seller' && <span style={{ fontSize: '0.8rem', opacity: 0.7 }}>(Current)</span>}
              </StatusOptionBtn>
              
              <StatusOptionBtn $bg="#FEF2F2" $fg="#B91C1C" $borderColor="#EF4444" $active={activeUser.role === 'admin'} onClick={() => handleRoleChange(activeUser.id, 'admin')} whileHover={{ scale: 1.02 }}>
                <FaUserShield /> <span style={{ flex: 1, textAlign: 'left' }}>Administrator</span> {activeUser.role === 'admin' && <span style={{ fontSize: '0.8rem', opacity: 0.7 }}>(Current)</span>}
              </StatusOptionBtn>
              
            </ModalCard>
          </ModalOverlay>
          </ModalPortal>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default UsersSection;

// STYLED COMPONENTS
const SectionTitle = styled.h2` color: #0F172A; margin-bottom: 1.5rem; font-size: 1.5rem; font-weight: 800; `;
const ListItem = styled(motion.li)` background: #ffffff; padding: 1.8rem; border-radius: 20px; margin-bottom: 1rem; display: flex; flex-direction: column; gap: 1rem; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid rgba(11, 132, 87, 0.08); @media (min-width: 768px) { flex-direction: row; justify-content: space-between; align-items: center; } `;
const ControlsWrapper = styled.div` display: flex; gap: 0.8rem; width: 100%; @media (min-width: 768px) { width: auto; align-items: center; } `;

const RoleTriggerButton = styled(motion.button)` 
  display: flex; align-items: center; justify-content: center; gap: 0.5rem; padding: 0.6rem 1.2rem; border-radius: 12px; font-size: 0.9rem; font-weight: 700; text-transform: uppercase; border: none; cursor: pointer; flex: 1; 
  background-color: ${props => props.$role === 'admin' ? '#FEF2F2' : props.$role === 'seller' ? '#DBEAFE' : '#ECFDF5'}; 
  color: ${props => props.$role === 'admin' ? '#B91C1C' : props.$role === 'seller' ? '#1D4ED8' : '#047857'}; 
  border: 1px solid ${props => props.$role === 'admin' ? 'rgba(239, 68, 68, 0.3)' : props.$role === 'seller' ? 'rgba(59, 130, 246, 0.3)' : 'rgba(16, 185, 129, 0.3)'};
  &:hover { filter: brightness(0.95); } 
  @media (min-width: 768px) { flex: initial; min-width: 150px; } 
`;

const DeleteButton = styled(motion.button)` padding: 0.6rem 1.2rem; background: #FEF2F2; color: #DC2626; border: 1px solid #FCA5A5; border-radius: 12px; font-size: 0.9rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; flex: 1; gap: 0.4rem; &:hover { background: #FEE2E2; } @media (min-width: 768px) { flex: initial; } `;

const PaginationWrapper = styled.div` display: flex; justify-content: center; align-items: center; gap: 1rem; margin-top: 3rem; padding-bottom: 1rem; `;
const PageButton = styled.button` padding: 0.6rem 1.4rem; border-radius: 50px; border: none; font-weight: 700; background: ${props => props.disabled ? '#F1F5F9' : '#0B8457'}; color: ${props => props.disabled ? '#94A3B8' : 'white'}; cursor: ${props => props.disabled ? 'not-allowed' : 'pointer'}; transition: 0.2s; box-shadow: ${props => props.disabled ? 'none' : '0 4px 10px rgba(11, 132, 87, 0.2)'}; &:hover:not(:disabled) { background: #086341; transform: translateY(-1px); } `;
const PageInfo = styled.span` font-weight: 700; color: #334155; font-size: 0.95rem; background: #ffffff; padding: 0.6rem 1.2rem; border-radius: 50px; border: 1px solid #E2E8F0; `;

const ModalOverlay = styled(motion.div)` position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 9999; padding: 1rem; `;
const ModalCard = styled(motion.div)` background: white; width: 90%; max-width: 420px; border-radius: 24px; padding: 2.5rem; position: relative; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); border: 1px solid rgba(11, 132, 87, 0.1); `;
const CloseButton = styled.button` position: absolute; top: 1.5rem; right: 1.5rem; background: none; border: none; font-size: 1.2rem; color: #94A3B8; cursor: pointer; &:hover { color: #0F172A; } `;
const StatusOptionBtn = styled(motion.button)` display: flex; align-items: center; gap: 1rem; width: 100%; padding: 1rem 1.2rem; margin-bottom: 0.8rem; border: 2px solid ${props => props.$active ? props.$borderColor : 'transparent'}; border-radius: 14px; background-color: ${props => props.$bg}; color: ${props => props.$fg}; font-size: 1.05rem; font-weight: 700; cursor: pointer; &:hover { filter: brightness(0.95); } `;

const ConfirmOverlay = styled(motion.div)` position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 10000; padding: 1rem; `;
const ConfirmCard = styled(motion.div)` background: white; padding: 2.5rem; border-radius: 24px; width: 100%; max-width: 420px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); h3 { margin-top: 0; color: #0F172A; font-weight: 800; } p { color: #64748B; margin-bottom: 2rem; line-height: 1.5; } `;
const ButtonGroup = styled.div` display: flex; gap: 1rem; justify-content: center; `;
const ConfirmDeleteBtn = styled.button` padding: 0.9rem 1.5rem; border: none; border-radius: 12px; cursor: pointer; font-weight: 700; background: #EF4444; color: #ffffff; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2); &:hover { background: #DC2626; } `;
const CancelBtn = styled.button` padding: 0.9rem 1.5rem; border: 1px solid #E2E8F0; border-radius: 12px; cursor: pointer; font-weight: 700; background: #ffffff; color: #475569; &:hover { background: #F8FAFC; color: #0F172A; } `;