// src/sections/CategoriesSection.jsx
import { useState, useEffect, useContext } from 'react';
import styled from 'styled-components';
import { motion, AnimatePresence } from 'framer-motion';
import AuthContext from '../context/AuthContext';
import { toast } from "react-hot-toast";
import { FaTimes, FaPlus, FaEdit, FaTrash } from 'react-icons/fa';
import ModalPortal from '../components/ModalPortal';

const CategoriesSection = () => {
  const { axiosInstance } = useContext(AuthContext);
  const [categories, setCategories] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form, setForm] = useState({ name: '' });
  const [editId, setEditId] = useState(null);

  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [categoryToDelete, setCategoryToDelete] = useState(null);

  const fetchCategories = async () => {
    const res = await axiosInstance.get('/api/categories/');
    setCategories(res.data);
  };
  // eslint-disable-next-line
  useEffect(() => { fetchCategories(); }, []);

  const handleOpenModal = (category = null) => {
    if (category) { setForm({ name: category.name }); setEditId(category.id); } 
    else { setForm({ name: '' }); setEditId(null); }
    setIsModalOpen(true);
  };

  const handleSubmit = async () => {
    if (!form.name.trim()) return toast.error('Category name cannot be empty');
    try {
      if (editId) {
        await axiosInstance.put(`/api/categories/${editId}/`, form);
        toast.success('✏️ Category updated');
      } else {
        await axiosInstance.post('/api/categories/', form);
        toast.success('📂 Category added');
      }
      setIsModalOpen(false);
      fetchCategories();
    } catch { toast.error('❌ Failed to save category'); }
  };

  const promptDelete = (id) => {
    setCategoryToDelete(id);
    setIsDeleteModalOpen(true);
  };

  const executeDelete = async () => {
    if (!categoryToDelete) return;
    try {
      await axiosInstance.delete(`/api/categories/${categoryToDelete}/`);
      toast.success('✅ Category deleted');
      fetchCategories();
    } catch { 
      toast.error('❌ Failed to delete category'); 
    } finally {
      setIsDeleteModalOpen(false);
      setCategoryToDelete(null);
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <SectionTitle>
        <span>📂 Manage Categories</span>
        <AddNewButton onClick={() => handleOpenModal()} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
          <FaPlus /> Add Category
        </AddNewButton>
      </SectionTitle>

      <ul style={{ padding: 0, listStyle: 'none' }}>
        {categories.map(c => (
          <ListItem key={c.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} whileHover={{ y: -2 }}>
            <div style={{ fontWeight: '800', fontSize: '1.15rem', color: '#0F172A' }}>{c.name}</div>
            <ActionRow>
              <ActionButton $bg="#3B82F6" onClick={() => handleOpenModal(c)} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}><FaEdit/> Edit</ActionButton>
              <ActionButton $bg="#EF4444" onClick={() => promptDelete(c.id)} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}><FaTrash/> Delete</ActionButton>
            </ActionRow>
          </ListItem>
        ))}
      </ul>

      {/* --- Delete Confirmation Modal --- */}
      <AnimatePresence>
        {isDeleteModalOpen && (
          <ModalPortal>
          <ConfirmOverlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <ConfirmCard initial={{ scale: 0.9, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.9, opacity: 0, y: 10 }}>
              <h3>Delete Category</h3>
              <p>Delete this category? This might break product assignments.</p>
              <ButtonGroup>
                <CancelBtn onClick={() => setIsDeleteModalOpen(false)}>Cancel</CancelBtn>
                <ConfirmDeleteBtn onClick={executeDelete}>Yes, Delete</ConfirmDeleteBtn>
              </ButtonGroup>
            </ConfirmCard>
          </ConfirmOverlay>
          </ModalPortal>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isModalOpen && (
          <ModalPortal>
          <ModalOverlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setIsModalOpen(false)}>
            <ModalCard initial={{ scale: 0.9, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.9, opacity: 0, y: 10 }} onClick={e => e.stopPropagation()}>
              <CloseButton onClick={() => setIsModalOpen(false)}><FaTimes /></CloseButton>
              <h3 style={{ margin: '0 0 1.5rem 0', color: '#0F172A', fontSize: '1.4rem', fontWeight: '800' }}>{editId ? 'Update Category' : 'Add Category'}</h3>
              <AdminInput placeholder="Enter Category Name" value={form.name} onChange={e => setForm({ name: e.target.value })} autoFocus />
              <SaveButton onClick={handleSubmit} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                {editId ? 'Save Changes' : 'Create Category'}
              </SaveButton>
            </ModalCard>
          </ModalOverlay>
          </ModalPortal>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default CategoriesSection;

// --- Styled Components ---
const SectionTitle = styled.h2` color: #0F172A; margin-bottom: 1.5rem; font-size: 1.5rem; font-weight: 800; display: flex; justify-content: space-between; align-items: center; `;
const AddNewButton = styled(motion.button)` background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%); color: white; border: none; padding: 0.7rem 1.4rem; border-radius: 50px; font-size: 0.95rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 0.5rem; box-shadow: 0 4px 14px rgba(11, 132, 87, 0.25); &:hover { box-shadow: 0 6px 20px rgba(11, 132, 87, 0.4); } `;
const ListItem = styled(motion.li)` background: #ffffff; padding: 1.5rem; border-radius: 20px; margin-bottom: 1rem; display: flex; flex-direction: column; gap: 1rem; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid rgba(11, 132, 87, 0.08); @media (min-width: 768px) { flex-direction: row; justify-content: space-between; align-items: center; } `;
const ActionRow = styled.div` display: flex; gap: 0.6rem; `;
const ActionButton = styled(motion.button)` padding: 0.6rem 1.2rem; border: none; border-radius: 12px; font-size: 0.9rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 0.4rem; color: white; background: ${props => props.$bg || '#3B82F6'}; box-shadow: 0 2px 8px rgba(0,0,0,0.05); &:hover { filter: brightness(0.95); } `;

const ModalOverlay = styled(motion.div)` position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 9999; padding: 1rem; `;
const ModalCard = styled(motion.div)` background: white; width: 90%; max-width: 440px; border-radius: 24px; padding: 2.5rem; position: relative; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); border: 1px solid rgba(11, 132, 87, 0.1); `;
const CloseButton = styled.button` position: absolute; top: 1.5rem; right: 1.5rem; background: none; border: none; font-size: 1.2rem; color: #94A3B8; cursor: pointer; &:hover { color: #0F172A; } `;
const AdminInput = styled.input` width: 100%; padding: 0.9rem 1.2rem; margin-bottom: 1.5rem; border: 1px solid #E2E8F0; border-radius: 12px; font-size: 1rem; background: #F8FAFC; color: #0F172A; box-sizing: border-box; &:focus { outline: none; border-color: #0B8457; background: #ffffff; box-shadow: 0 0 0 3px rgba(11, 132, 87, 0.1); } `;
const SaveButton = styled(motion.button)` width: 100%; padding: 1rem; background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%); color: white; border: none; border-radius: 14px; font-size: 1.05rem; font-weight: 800; cursor: pointer; box-shadow: 0 6px 20px rgba(11, 132, 87, 0.25); &:hover { box-shadow: 0 8px 25px rgba(11, 132, 87, 0.4); } `;

// Confirm Modal Styling
const ConfirmOverlay = styled(motion.div)` position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 10000; padding: 1rem; `;
const ConfirmCard = styled(motion.div)` background: white; padding: 2.5rem; border-radius: 24px; width: 100%; max-width: 420px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); h3 { margin-top: 0; color: #0F172A; font-weight: 800; } p { color: #64748B; margin-bottom: 2rem; line-height: 1.5; } `;
const ButtonGroup = styled.div` display: flex; gap: 1rem; justify-content: center; `;
const ConfirmDeleteBtn = styled.button` padding: 0.9rem 1.5rem; border: none; border-radius: 12px; cursor: pointer; font-weight: 700; background: #EF4444; color: #ffffff; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2); &:hover { background: #DC2626; } `;
const CancelBtn = styled.button` padding: 0.9rem 1.5rem; border: 1px solid #E2E8F0; border-radius: 12px; cursor: pointer; font-weight: 700; background: #ffffff; color: #475569; &:hover { background: #F8FAFC; color: #0F172A; } `;