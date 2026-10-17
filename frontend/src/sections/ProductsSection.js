// src/sections/ProductsSection.jsx
import { useEffect, useState, useContext } from 'react';
import styled from 'styled-components';
import { motion, AnimatePresence } from 'framer-motion';
import AuthContext from '../context/AuthContext';
import { toast } from "react-hot-toast";
import { FaTimes, FaPlus, FaEdit, FaTrash, FaCheckCircle, FaStore } from 'react-icons/fa';
import ModalPortal from '../components/ModalPortal';
import { formatINR } from '../utils/currency';

const ProductsSection = () => {
  const { axiosInstance } = useContext(AuthContext);
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const emptyForm = { name: '', description: '', price: '', stock: '', category: '', image_url: '' };
  const [form, setForm] = useState(emptyForm);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [productToDelete, setProductToDelete] = useState(null);
  const [isApproving, setIsApproving] = useState(null);

  const fetchProducts = async () => {
    try {
      const res = await axiosInstance.get(`/api/products/?page=${currentPage}`);
      setProducts(res.data.results || res.data);
      if (res.data.count) setTotalPages(Math.ceil(res.data.count / 12));
    } catch { setProducts([]); }
  };

  useEffect(() => {
    fetchProducts();
    axiosInstance.get('/api/categories/').then(res => setCategories(res.data.results || res.data)).catch(() => setCategories([]));
    // eslint-disable-next-line
  }, [axiosInstance, currentPage]);

  const handleOpenModal = (product = null) => {
    if (product) {
      setForm({ name: product.name, description: product.description, price: product.price, stock: product.stock, category: product.category, image_url: product.image_url });
      setEditId(product.id);
    } else {
      setForm(emptyForm);
      setEditId(null);
    }
    setIsModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      if (editId) {
        await axiosInstance.put(`/api/products/${editId}/`, form);
        toast.success('✏️ Product updated successfully');
      } else {
        await axiosInstance.post('/api/products/', form);
        toast.success('✅ Product added successfully');
      }
      setIsModalOpen(false);
      fetchProducts();
    } catch { toast.error('❌ Error saving product'); }
  };

  const executeDelete = async () => {
    if (!productToDelete) return;
    try {
      await axiosInstance.delete(`/api/products/${productToDelete}/`);
      toast.success('🗑️ Product deleted successfully');
      fetchProducts();
    } catch { toast.error('❌ Error deleting product'); } 
    finally { setIsDeleteModalOpen(false); setProductToDelete(null); }
  };

  const handleApprove = async (id) => {
    setIsApproving(id);
    try {
      await axiosInstance.post(`/api/products/${id}/approve/`);
      toast.success('✅ Product approved and is now live!');
      fetchProducts(); 
    } catch (err) {
      toast.error('❌ Error approving product');
    } finally {
      setIsApproving(null);
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <SectionTitle>
        <span>📦 Manage Products</span>
        <AddNewButton onClick={() => handleOpenModal()} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}><FaPlus /> Add Product</AddNewButton>
      </SectionTitle>

      <ul style={{ padding: 0, listStyle: 'none' }}>
        {products.map(p => (
          <ListItem key={p.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} whileHover={{ y: -2 }}>
            <ContentColumn>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                <div style={{ fontSize: '1.15rem', fontWeight: '800', color: '#0F172A' }}>
                  {p.name} - <span style={{ color: '#0B8457', fontWeight: '900' }}>{formatINR(p.price)}</span>
                </div>
                <StatusBadge className={p.approval_status || 'approved'}>
                  {p.approval_status ? p.approval_status.toUpperCase() : 'APPROVED'}
                </StatusBadge>
              </div>
              
              <div style={{ fontSize: '0.85rem', color: '#64748B', display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '0.3rem' }}>
                 <FaStore /> Sold by: <strong style={{ color: '#0F172A' }}>{p.vendor_name || 'EazyShop Official'}</strong>
              </div>

              <div style={{ color: p.stock > 0 ? '#475569' : '#EF4444', fontSize: '0.9rem', fontWeight: '700', marginTop: '0.3rem' }}>Inventory: {p.stock} units</div>
              <div style={{ fontSize: '0.9rem', color: '#64748B', maxWidth: '100%', marginTop: '0.2rem' }}>{p.description ? `${p.description.substring(0, 80)}...` : 'No description provided.'}</div>
            </ContentColumn>
            <ActionRow>
              {p.approval_status === 'pending' && (
                <ActionButton 
                  $bg="#F59E0B" 
                  onClick={() => handleApprove(p.id)} 
                  disabled={isApproving === p.id}
                  whileHover={{ scale: 1.05 }} 
                  whileTap={{ scale: 0.95 }}
                >
                  <FaCheckCircle /> {isApproving === p.id ? 'Approving...' : 'Approve'}
                </ActionButton>
              )}
              <ActionButton $bg="#3B82F6" onClick={() => handleOpenModal(p)} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}><FaEdit /> Edit</ActionButton>
              <ActionButton $bg="#EF4444" onClick={() => { setProductToDelete(p.id); setIsDeleteModalOpen(true); }} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}><FaTrash /> Delete</ActionButton>
            </ActionRow>
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
              <h3>Delete Product</h3>
              <p>Are you sure you want to delete this product? This action cannot be undone.</p>
              <ButtonGroup>
                <CancelBtn onClick={() => setIsDeleteModalOpen(false)}>Cancel</CancelBtn>
                <ConfirmDeleteBtn onClick={executeDelete}>Yes, Delete</ConfirmDeleteBtn>
              </ButtonGroup>
            </ConfirmCard>
          </ConfirmOverlay>
          </ModalPortal>
        )}
        {isModalOpen && (
          <ModalPortal>
          <ModalOverlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setIsModalOpen(false)}>
            <ModalCard initial={{ scale: 0.9, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.9, opacity: 0, y: 10 }} onClick={e => e.stopPropagation()}>
              <CloseButton onClick={() => setIsModalOpen(false)}><FaTimes /></CloseButton>
              <h3 style={{ margin: '0 0 1.5rem 0', color: '#0F172A', fontSize: '1.4rem', fontWeight: '800' }}>{editId ? 'Update Product' : 'Add New Product'}</h3>
              <AdminInput placeholder="Product Name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
              <AdminTextarea placeholder="Description" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <AdminInput placeholder="Price (₹)" type="number" value={form.price} onChange={e => setForm({ ...form, price: parseFloat(e.target.value) || '' })} />
                <AdminInput placeholder="Stock" type="number" value={form.stock} onChange={e => setForm({ ...form, stock: parseInt(e.target.value) || '' })} />
              </div>
              <AdminSelect value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>
                <option value="">Select Category</option>
                {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </AdminSelect>
              <AdminInput placeholder="Image URL" value={form.image_url} onChange={e => setForm({ ...form, image_url: e.target.value })} />
              <SaveButton onClick={handleSubmit} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>{editId ? 'Save Changes' : 'Create Product'}</SaveButton>
            </ModalCard>
          </ModalOverlay>
          </ModalPortal>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default ProductsSection;

// STYLED COMPONENTS
const SectionTitle = styled.h2` color: #0F172A; margin-bottom: 1.5rem; font-size: 1.5rem; font-weight: 800; display: flex; justify-content: space-between; align-items: center; `;
const AddNewButton = styled(motion.button)` background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%); color: white; border: none; padding: 0.7rem 1.4rem; border-radius: 50px; font-size: 0.95rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 0.5rem; box-shadow: 0 4px 14px rgba(11, 132, 87, 0.25); &:hover { box-shadow: 0 6px 20px rgba(11, 132, 87, 0.4); } `;
const ListItem = styled(motion.li)` background: #ffffff; padding: 1.8rem; border-radius: 20px; margin-bottom: 1rem; display: flex; flex-direction: column; gap: 1rem; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid rgba(11, 132, 87, 0.08); @media (min-width: 768px) { flex-direction: row; justify-content: space-between; align-items: flex-start; } `;
const ContentColumn = styled.div` display: flex; flex-direction: column; gap: 0.2rem; flex: 1; `;
const ActionRow = styled.div` display: flex; gap: 0.6rem; flex-wrap: wrap; justify-content: flex-end; align-items: flex-start; `;
const ActionButton = styled(motion.button)` padding: 0.6rem 1.2rem; border: none; border-radius: 12px; font-size: 0.9rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 0.4rem; color: white; background: ${props => props.$bg}; box-shadow: 0 2px 8px rgba(0,0,0,0.05); &:hover { filter: brightness(0.95); } &:disabled { opacity: 0.6; cursor: not-allowed; } `;

const StatusBadge = styled.span` 
  font-size: 0.75rem; font-weight: 800; padding: 0.3rem 0.8rem; border-radius: 50px; text-transform: uppercase; letter-spacing: 0.5px;
  &.approved { background: #ECFDF5; color: #047857; border: 1px solid rgba(16, 185, 129, 0.3); } 
  &.pending { background: #FEF3C7; color: #B45309; border: 1px solid rgba(245, 158, 11, 0.3); } 
  &.rejected { background: #FEF2F2; color: #DC2626; border: 1px solid rgba(239, 68, 68, 0.3); } 
`;

const PaginationWrapper = styled.div` display: flex; justify-content: center; align-items: center; gap: 1rem; margin-top: 3rem; padding-bottom: 1rem; `;
const PageButton = styled.button` padding: 0.6rem 1.4rem; border-radius: 50px; border: none; font-weight: 700; background: ${props => props.disabled ? '#F1F5F9' : '#0B8457'}; color: ${props => props.disabled ? '#94A3B8' : 'white'}; cursor: ${props => props.disabled ? 'not-allowed' : 'pointer'}; transition: 0.2s; box-shadow: ${props => props.disabled ? 'none' : '0 4px 10px rgba(11, 132, 87, 0.2)'}; &:hover:not(:disabled) { background: #086341; transform: translateY(-1px); } `;
const PageInfo = styled.span` font-weight: 700; color: #334155; font-size: 0.95rem; background: #ffffff; padding: 0.6rem 1.2rem; border-radius: 50px; border: 1px solid #E2E8F0; `;

const ModalOverlay = styled(motion.div)` position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 9999; padding: 1rem; `;
const ModalCard = styled(motion.div)` background: white; width: 100%; max-width: 500px; border-radius: 24px; padding: 2.5rem; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); position: relative; max-height: 90vh; overflow-y: auto; border: 1px solid rgba(11, 132, 87, 0.1); `;
const CloseButton = styled.button` position: absolute; top: 1.5rem; right: 1.5rem; background: none; border: none; font-size: 1.2rem; color: #94A3B8; cursor: pointer; &:hover { color: #0F172A; } `;

const AdminInput = styled.input` width: 100%; padding: 0.9rem 1.2rem; margin-bottom: 1rem; border: 1px solid #E2E8F0; border-radius: 12px; font-size: 1rem; background: #F8FAFC; color: #0F172A; box-sizing: border-box; &:focus { outline: none; border-color: #0B8457; background: #ffffff; box-shadow: 0 0 0 3px rgba(11, 132, 87, 0.1); } `;
const AdminTextarea = styled.textarea` width: 100%; padding: 0.9rem 1.2rem; margin-bottom: 1rem; min-height: 100px; resize: vertical; border: 1px solid #E2E8F0; border-radius: 12px; font-size: 1rem; background: #F8FAFC; color: #0F172A; box-sizing: border-box; &:focus { outline: none; border-color: #0B8457; background: #ffffff; box-shadow: 0 0 0 3px rgba(11, 132, 87, 0.1); } `;
const AdminSelect = styled.select` width: 100%; padding: 0.9rem 1.2rem; margin-bottom: 1rem; border: 1px solid #E2E8F0; border-radius: 12px; font-size: 1rem; background: #F8FAFC; color: #0F172A; box-sizing: border-box; &:focus { outline: none; border-color: #0B8457; background: #ffffff; box-shadow: 0 0 0 3px rgba(11, 132, 87, 0.1); } `;

const SaveButton = styled(motion.button)` width: 100%; padding: 1rem; background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%); color: white; border: none; border-radius: 14px; font-size: 1.05rem; font-weight: 800; cursor: pointer; margin-top: 0.5rem; box-shadow: 0 6px 20px rgba(11, 132, 87, 0.25); &:hover { box-shadow: 0 8px 25px rgba(11, 132, 87, 0.4); } `;

const ConfirmOverlay = styled(motion.div)` position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 10000; padding: 1rem; `;
const ConfirmCard = styled(motion.div)` background: white; padding: 2.5rem; border-radius: 24px; width: 100%; max-width: 420px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); h3 { margin-top: 0; color: #0F172A; font-weight: 800; } p { color: #64748B; margin-bottom: 2rem; line-height: 1.5; } `;
const ButtonGroup = styled.div` display: flex; gap: 1rem; justify-content: center; margin-top: 2rem;`;
const ConfirmDeleteBtn = styled.button` padding: 0.9rem 1.5rem; border: none; border-radius: 12px; cursor: pointer; font-weight: 700; background: #EF4444; color: #ffffff; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2); &:hover { background: #DC2626; } `;
const CancelBtn = styled.button` padding: 0.9rem 1.5rem; border: 1px solid #E2E8F0; border-radius: 12px; cursor: pointer; font-weight: 700; background: #ffffff; color: #475569; &:hover { background: #F8FAFC; color: #0F172A; } `;