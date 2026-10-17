// src/sections/vendor/VendorProductsSection.jsx
import { useState, useContext, useEffect } from 'react';
import styled from 'styled-components';
import { motion, AnimatePresence } from 'framer-motion';
import { FaBox, FaPlus, FaEdit, FaTrash, FaTimes, FaTag, FaImage, FaExclamationTriangle } from 'react-icons/fa';
import { toast } from 'react-hot-toast';
import AuthContext from '../../context/AuthContext';
import ModalPortal from '../../components/ModalPortal';
import { formatINR } from '../../utils/currency';

// ==========================================
// PRODUCT ADD/EDIT MODAL
// ==========================================
const ProductModal = ({ isOpen, onClose, onSubmit, initialData, categories, isSubmitting }) => {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    price: '',
    stock: '',
    category: '',
    image_url: ''
  });

  useEffect(() => {
    if (isOpen) {
      if (initialData) {
        setFormData({
          name: initialData.name || '',
          description: initialData.description || '',
          price: initialData.price || '',
          stock: initialData.stock || '',
          category: initialData.category || '',
          image_url: initialData.image_url || ''
        });
      } else {
        setFormData({ name: '', description: '', price: '', stock: '', category: '', image_url: '' });
      }
    }
  }, [isOpen, initialData]);

  if (!isOpen) return null;

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = () => {
    if (!formData.name || !formData.price || !formData.stock || !formData.category || !formData.image_url) {
      return toast.error("Please fill in all required fields.");
    }
    onSubmit(formData);
  };

  return (
  <ModalPortal>
    <Overlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <ModalCard initial={{ scale: 0.95, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.95, opacity: 0, y: 10 }} style={{ maxWidth: '550px' }}>
        <CloseBtn onClick={onClose}><FaTimes /></CloseBtn>
        <ModalIconWrapper><FaBox size={22} color="#0B8457" /></ModalIconWrapper>
        <h3>{initialData ? 'Edit Product' : 'Add New Product'}</h3>
        <p>{initialData ? 'Update your listing details.' : 'List a new product on the marketplace.'}</p>
        
        <ModalContentWrapper>
          <FormGroup>
            <label>Product Name</label>
            <InputField type="text" name="name" value={formData.name} onChange={handleChange} placeholder="e.g. Wireless Noise-Cancelling Headphones" />
          </FormGroup>

          <GridRow>
            <FormGroup>
              <label>Price (₹)</label>
              <InputField type="number" step="0.01" name="price" value={formData.price} onChange={handleChange} placeholder="0.00" />
            </FormGroup>
            <FormGroup>
              <label>Stock Quantity</label>
              <InputField type="number" name="stock" value={formData.stock} onChange={handleChange} placeholder="0" />
            </FormGroup>
          </GridRow>

          <FormGroup>
            <label>Category</label>
            <select name="category" value={formData.category} onChange={handleChange}>
              <option value="">-- Select a Category --</option>
              {categories.map(cat => (
                <option key={cat.id} value={cat.id}>{cat.name}</option>
              ))}
            </select>
          </FormGroup>

          <FormGroup>
            <label>Image URL</label>
            <InputField type="url" name="image_url" value={formData.image_url} onChange={handleChange} placeholder="https://example.com/image.jpg" />
          </FormGroup>

          <FormGroup>
            <label>Description</label>
            <textarea name="description" rows="3" value={formData.description} onChange={handleChange} placeholder="Describe the product's features and benefits..." />
          </FormGroup>

          <ButtonGroup style={{ marginTop: '0.5rem' }}>
            <ModalSecondaryButton onClick={onClose} disabled={isSubmitting}>Cancel</ModalSecondaryButton>
            <ModalPrimaryButton onClick={handleSubmit} disabled={isSubmitting}>
              {isSubmitting ? 'Saving...' : 'Save Product'}
            </ModalPrimaryButton>
          </ButtonGroup>
        </ModalContentWrapper>
      </ModalCard>
    </Overlay>
    </ModalPortal>
  );
};

// ==========================================
// VENDOR PRODUCTS SECTION COMPONENT
// ==========================================
const VendorProductsSection = () => {
  const { user, axiosInstance } = useContext(AuthContext);
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  
  const [modalConfig, setModalConfig] = useState({ isOpen: false, initialData: null });
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 🚀 New state for the custom deletion modal
  const [deleteModalConfig, setDeleteModalConfig] = useState({ isOpen: false, productId: null, productName: '' });
  const [isDeleting, setIsDeleting] = useState(false);

  const fetchCatalogData = async () => {
    setIsLoading(true);
    try {
      const [prodRes, catRes] = await Promise.all([
        axiosInstance.get(`/api/products/?vendor=${user.id}`),
        axiosInstance.get('/api/categories/')
      ]);
      
      setProducts(prodRes.data.results || prodRes.data);
      setCategories(catRes.data.results || catRes.data);
    } catch (error) {
      toast.error('❌ Failed to load catalog data.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchCatalogData();
    // eslint-disable-next-line
  }, []);

  const handleOpenModal = (product = null) => {
    setModalConfig({ isOpen: true, initialData: product });
  };

  const handleCloseModal = () => {
    setModalConfig({ isOpen: false, initialData: null });
  };

  const handleSaveProduct = async (formData) => {
    setIsSubmitting(true);
    try {
      if (modalConfig.initialData) {
        await axiosInstance.patch(`/api/products/${modalConfig.initialData.id}/`, formData);
        toast.success('📦 Product updated successfully!');
      } else {
        await axiosInstance.post('/api/products/', formData);
        toast.success('📦 Product submitted for approval!');
      }
      fetchCatalogData();
      handleCloseModal();
    } catch (err) {
      toast.error('❌ Failed to save product. Please check the fields.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const triggerDeletePrompt = (id, name) => {
    setDeleteModalConfig({ isOpen: true, productId: id, productName: name });
  };

  const executeDeleteProduct = async () => {
    setIsDeleting(true);
    try {
      await axiosInstance.delete(`/api/products/${deleteModalConfig.productId}/`);
      setProducts(prev => prev.filter(p => p.id !== deleteModalConfig.productId));
      toast.success('🗑️ Product removed permanently.');
      setDeleteModalConfig({ isOpen: false, productId: null, productName: '' });
    } catch (err) {
      toast.error('❌ Failed to delete product.');
    } finally {
      setIsDeleting(false);
    }
  };

  const getCategoryName = (catId) => {
    const cat = categories.find(c => c.id === catId);
    return cat ? cat.name : 'Uncategorized';
  };

  if (isLoading) {
    return <LoadingWrapper><Spinner /><LoadingText>Loading Catalog...</LoadingText></LoadingWrapper>;
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <AnimatePresence>
        {modalConfig.isOpen && (
          <ProductModal 
            isOpen={modalConfig.isOpen} 
            onClose={handleCloseModal} 
            onSubmit={handleSaveProduct} 
            initialData={modalConfig.initialData} 
            categories={categories}
            isSubmitting={isSubmitting} 
          />
        )}
      </AnimatePresence>

      {/* 🚀 SaaS-Level Delete Confirmation Modal using ModalPortal */}
      <AnimatePresence>
        {deleteModalConfig.isOpen && (
          <ModalPortal>
            <Overlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <ModalCard initial={{ scale: 0.95, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.95, opacity: 0, y: 10 }}>
                <ModalDangerIconWrapper>
                  <FaExclamationTriangle size={24} color="#DC2626" />
                </ModalDangerIconWrapper>
                <h3>Delete Product?</h3>
                <p>Are you sure you want to permanently remove <strong>"{deleteModalConfig.productName}"</strong> from your catalog? This action cannot be undone.</p>
                <ButtonGroup style={{ marginTop: '1.5rem' }}>
                  <ModalSecondaryButton onClick={() => setDeleteModalConfig({ isOpen: false, productId: null, productName: '' })} disabled={isDeleting}>Cancel</ModalSecondaryButton>
                  <ModalDangerButton onClick={executeDeleteProduct} disabled={isDeleting}>
                    {isDeleting ? 'Deleting...' : 'Yes, Delete'}
                  </ModalDangerButton>
                </ButtonGroup>
              </ModalCard>
            </Overlay>
          </ModalPortal>
        )}
      </AnimatePresence>

      <SectionHeader>
        <div>
          <h2 style={{ margin: 0, color: '#0F172A', fontSize: '1.4rem', fontWeight: '800' }}>My Catalog</h2>
          <p style={{ margin: '0.2rem 0 0 0', color: '#64748B', fontSize: '0.95rem' }}>Manage your inventory and track approval statuses.</p>
        </div>
        <AddButton onClick={() => handleOpenModal()} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}><FaPlus /> Add New Product</AddButton>
      </SectionHeader>

      {products.length === 0 ? (
        <EmptyState>
          <span className="emoji">🏷️</span>
          <h3>Your catalog is empty</h3>
          <p>Start listing products to make sales!</p>
        </EmptyState>
      ) : (
        <ProductGrid>
          {products.map((product) => (
            <ProductCard key={product.id} whileHover={{ y: -4 }} transition={{ duration: 0.2 }}>
              <div className="img-container">
                {product.image_url ? (
                  <img src={product.image_url} alt={product.name} />
                ) : (
                  <div className="no-img"><FaImage size={32} color="#CBD5E1" /></div>
                )}
                <span className={`status-badge ${product.approval_status || 'pending'}`}>
                  {(product.approval_status || 'pending').toUpperCase()}
                </span>
              </div>
              
              <div className="details">
                <h4 className="truncate">{product.name}</h4>
                <div className="meta">
                  <span className="price">{formatINR(product.price)}</span>
                  <span className="stock">Stock: {product.stock}</span>
                </div>
                <p className="category"><FaTag size={12} /> {getCategoryName(product.category)}</p>
                
                <div className="actions">
                  <button className="edit" onClick={() => handleOpenModal(product)}><FaEdit /> Edit</button>
                  <button className="delete" onClick={() => triggerDeletePrompt(product.id, product.name)}><FaTrash /></button>
                </div>
              </div>
            </ProductCard>
          ))}
        </ProductGrid>
      )}
    </motion.div>
  );
};

export default VendorProductsSection;

// ==========================================
// STYLED COMPONENTS 
// ==========================================

const LoadingWrapper = styled.div` display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 4rem 0; `;
const Spinner = styled.div` width: 45px; height: 45px; border: 4px solid #E2E8F0; border-top: 4px solid #0B8457; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 1rem; @keyframes spin { to { transform: rotate(360deg); } } `;
const LoadingText = styled.div` font-size: 1.1rem; font-weight: 600; color: #0B8457; `;

const SectionHeader = styled.div` 
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; flex-wrap: wrap; gap: 1rem; background: #ffffff; padding: 1.8rem 2.2rem; border-radius: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid rgba(11, 132, 87, 0.08); 
`;

const AddButton = styled(motion.button)` 
  display: flex; align-items: center; gap: 0.5rem; background: #ECFDF5; color: #0B8457; border: 1px solid rgba(16, 185, 129, 0.3); padding: 0.7rem 1.4rem; border-radius: 12px; cursor: pointer; font-weight: 700; font-size: 0.95rem; transition: background 0.2s; 
  &:hover { background: #D1FAE5; } 
`;

const EmptyState = styled.div` 
  text-align: center; padding: 5rem 2rem; background: #ffffff; border-radius: 24px; border: 1px dashed #CBD5E1; 
  .emoji { font-size: 3.5rem; display: block; margin-bottom: 1rem; }
  h3 { color: #0F172A; font-size: 1.5rem; font-weight: 800; margin-bottom: 0.5rem; }
  p { color: #64748B; font-size: 1rem; } 
`;

const ProductGrid = styled.div` display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem; `;

const ProductCard = styled(motion.div)` 
  background: white; 
  border-radius: 20px; 
  overflow: hidden; 
  box-shadow: 0 4px 20px rgba(0,0,0,0.03); 
  border: 1px solid rgba(11, 132, 87, 0.08); 
  display: flex; 
  flex-direction: column; 
  
  .img-container { 
    position: relative; 
    height: 200px;
    background: #ffffff;
    border-bottom: 1px solid #F1F5F9; 
    padding: 1rem;
    box-sizing: border-box;

    img { 
      width: 100%; 
      height: 100%; 
      object-fit: contain; 
      mix-blend-mode: multiply;
    } 
    .no-img { 
      width: 100%; height: 100%; display: flex; justify-content: center; align-items: center; 
    } 
    .status-badge { 
      position: absolute; top: 12px; right: 12px; padding: 0.3rem 0.8rem; border-radius: 50px; font-size: 0.75rem; font-weight: 800; box-shadow: 0 2px 8px rgba(0,0,0,0.05); 
    }
    .status-badge.approved { background: #ECFDF5; color: #047857; border: 1px solid rgba(16, 185, 129, 0.3); }
    .status-badge.pending { background: #FEF3C7; color: #B45309; border: 1px solid rgba(245, 158, 11, 0.3); }
    .status-badge.rejected { background: #FEF2F2; color: #DC2626; border: 1px solid rgba(239, 68, 68, 0.3); }
  }
  .details { 
    padding: 1.5rem; display: flex; flex-direction: column; flex: 1; 
    h4 { margin: 0 0 0.5rem 0; color: #0F172A; font-size: 1.1rem; font-weight: 700; } 
    .truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; .price { font-size: 1.25rem; font-weight: 900; color: #0B8457; } .stock { font-size: 0.9rem; color: #64748B; font-weight: 700; } }
    .category { color: #94A3B8; font-size: 0.85rem; display: flex; align-items: center; gap: 0.4rem; margin: 0 0 1.5rem 0; font-weight: 500; }
    .actions { display: flex; justify-content: space-between; gap: 0.6rem; margin-top: auto; 
      button { flex: 1; padding: 0.7rem; border: none; border-radius: 12px; font-weight: 700; cursor: pointer; transition: 0.2s; display: flex; justify-content: center; align-items: center; gap: 0.4rem; font-size: 0.9rem; }
      .edit { background: #F8FAFC; color: #334155; border: 1px solid #E2E8F0; &:hover { background: #E2E8F0; color: #0F172A; } }
      .delete { background: #FEF2F2; color: #DC2626; border: 1px solid #FCA5A5; &:hover { background: #FEE2E2; } }
    }
  }
`;

// MODAL UI
const Overlay = styled(motion.div)` 
  position: fixed; 
  inset: 0; 
  background: rgba(15, 23, 42, 0.6); 
  backdrop-filter: blur(8px); 
  display: flex; 
  align-items: center; 
  justify-content: center; 
  z-index: 1000; 
  padding: 1rem; 
  /* 🚀 FIX: Keeps overlay padding strictly within boundaries */
  box-sizing: border-box; 
`;

const ModalCard = styled(motion.div)` 
  position: relative; 
  background: white; 
  padding: 2.5rem; 
  border-radius: 24px; 
  width: 100%; 
  max-width: 440px; 
  text-align: center; 
  box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); 
  border: 1px solid rgba(11, 132, 87, 0.1);
  
  /* 🚀 CRITICAL FIX: Forces padding inside the box and enables internal scrolling */
  box-sizing: border-box;
  max-height: 90vh; /* Modal will never be taller than 90% of the screen */
  overflow-y: auto; /* Adds a scrollbar if the content is too tall */

  h3 { margin: 0 0 0.5rem 0; color: #0F172A; font-size: 1.5rem; font-weight: 800; } 
  p { color: #64748B; margin-bottom: 0; font-size: 0.95rem; }

  /* 🚀 MOBILE FIX: Shrink the heavy padding so the form can breathe */
  @media (max-width: 768px) {
    padding: 1.5rem 1.25rem;
    border-radius: 20px;
    
    h3 { font-size: 1.3rem; }
  }
`;

const ModalIconWrapper = styled.div` width: 55px; height: 55px; background: #ECFDF5; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem auto; `;
const ModalDangerIconWrapper = styled.div` width: 55px; height: 55px; background: #FEF2F2; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem auto; `;
const CloseBtn = styled.button` position: absolute; top: 1.2rem; right: 1.2rem; background: none; border: none; font-size: 1.2rem; color: #94A3B8; cursor: pointer; &:hover { color: #0F172A; } `;

const ModalContentWrapper = styled.div` display: flex; flex-direction: column; gap: 1rem; width: 100%; margin-top: 1.5rem; box-sizing: border-box; `;

const GridRow = styled.div` 
  display: grid; 
  grid-template-columns: 1fr 1fr; 
  gap: 1rem; 
  width: 100%; 
  box-sizing: border-box; 

  /* 🚀 MOBILE FIX: Stack the Price and Stock inputs on super small phones to prevent squishing */
  @media (max-width: 480px) {
    grid-template-columns: 1fr;
  }
`;
const FormGroup = styled.div` display: flex; flex-direction: column; gap: 0.4rem; text-align: left; width: 100%; box-sizing: border-box; 
  label { font-weight: 700; color: #0F172A; font-size: 0.9rem; } 
  select, textarea { width: 100%; padding: 0.9rem 1.2rem; border-radius: 12px; border: 1px solid #E2E8F0; font-size: 1rem; outline: none; font-family: inherit; box-sizing: border-box; transition: all 0.2s; background: #F8FAFC; color: #0F172A; &:focus { border-color: #0B8457; background: #ffffff; box-shadow: 0 0 0 3px rgba(11, 132, 87, 0.1); } } 
  select { background: #F8FAFC; cursor: pointer; } 
  textarea { resize: vertical; min-height: 80px; }
`;

const InputField = styled.input` width: 100%; padding: 0.9rem 1.2rem; border: 1px solid #E2E8F0; border-radius: 12px; font-size: 1rem; outline: none; box-sizing: border-box; font-family: inherit; background: #F8FAFC; color: #0F172A; transition: all 0.2s; &:focus { border-color: #0B8457; background: #ffffff; box-shadow: 0 0 0 3px rgba(11, 132, 87, 0.1); } `;

const ButtonGroup = styled.div` display: flex; gap: 1rem; width: 100%; justify-content: center; box-sizing: border-box; `;

const ModalPrimaryButton = styled.button` 
  flex: 1; padding: 0.9rem 0; border: none; border-radius: 12px; cursor: pointer; background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%); color: white; font-weight: 700; font-size: 1rem; box-shadow: 0 4px 12px rgba(11, 132, 87, 0.25); box-sizing: border-box; transition: all 0.2s; 
  &:hover:not(:disabled) { box-shadow: 0 6px 16px rgba(11, 132, 87, 0.35); } 
  &:disabled { opacity: 0.6; cursor: not-allowed; box-shadow: none; } 
`;

const ModalSecondaryButton = styled.button` 
  flex: 1; padding: 0.9rem 0; border: 1px solid #E2E8F0; border-radius: 12px; cursor: pointer; background: #ffffff; color: #475569; font-weight: 700; font-size: 1rem; box-sizing: border-box; transition: all 0.2s; 
  &:hover { background: #F8FAFC; color: #0F172A; } 
`;

const ModalDangerButton = styled.button`
  flex: 1; padding: 0.9rem 0; border: none; border-radius: 12px; cursor: pointer; background: #EF4444; color: #ffffff; font-weight: 700; font-size: 1rem; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2); transition: all 0.2s; box-sizing: border-box;
  &:hover:not(:disabled) { background: #DC2626; box-shadow: 0 6px 16px rgba(239, 68, 68, 0.3); }
  &:disabled { opacity: 0.6; cursor: not-allowed; box-shadow: none; }
`;