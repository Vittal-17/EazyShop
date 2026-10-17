// src/sections/dashboard/AddressSection.jsx
import { useState, useContext, useEffect } from 'react';
import styled from 'styled-components';
import { motion, AnimatePresence } from 'framer-motion';
import { FaMapMarkerAlt, FaPlus, FaStar, FaEdit, FaTrash, FaTimes, FaExclamationTriangle } from 'react-icons/fa';
import { toast } from "react-hot-toast";
import AuthContext from '../../context/AuthContext';
import ModalPortal from '../../components/ModalPortal';

const AddressModal = ({ isOpen, onClose, onSubmit, initialData, isSubmitting }) => {
  const [label, setLabel] = useState('Home');
  const [fullAddress, setFullAddress] = useState('');

  useEffect(() => {
    if (isOpen) {
      setLabel(initialData?.label || 'Home');
      setFullAddress(initialData?.full_address || '');
    }
  }, [isOpen, initialData]);

  if (!isOpen) return null;

  return (
    <ModalPortal>
    <Overlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <ModalCard initial={{ scale: 0.95, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.95, opacity: 0, y: 10 }}>
        <CloseBtn onClick={onClose}><FaTimes /></CloseBtn>
        <h3>{initialData ? 'Edit Address' : 'Add New Address'}</h3>
        <p>Enter your shipping destination details below.</p>
        
        <ModalContentWrapper>
          <FormGroup>
            <label>Address Label</label>
            <select value={label} onChange={e => setLabel(e.target.value)}>
              <option value="Home">Home</option>
              <option value="Work">Work</option>
              <option value="Other">Other</option>
            </select>
          </FormGroup>

          <FormGroup>
            <label>Full Delivery Address</label>
            <textarea rows="4" placeholder="House/Apt Number, Street, City, ZIP Code..." value={fullAddress} onChange={e => setFullAddress(e.target.value)} />
          </FormGroup>

          <ButtonGroup>
            <ModalSecondaryButton onClick={onClose} disabled={isSubmitting}>Cancel</ModalSecondaryButton>
            <ModalPrimaryButton onClick={() => onSubmit({ label, full_address: fullAddress })} disabled={isSubmitting || !fullAddress.trim()}>
              {isSubmitting ? 'Saving...' : 'Save Address'}
            </ModalPrimaryButton>
          </ButtonGroup>
        </ModalContentWrapper>
      </ModalCard>
    </Overlay>
    </ModalPortal>
  );
};

const AddressSection = ({ addresses, setAddresses }) => {
  const { axiosInstance } = useContext(AuthContext);
  const [addressModalData, setAddressModalData] = useState({ isOpen: false, initialData: null });
  const [isSubmittingAddress, setIsSubmittingAddress] = useState(false);

  // Wishlist-style Delete Confirmation Modal State
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [addressToRemove, setAddressToRemove] = useState(null);

  const openAddressModal = (address = null) => setAddressModalData({ isOpen: true, initialData: address });
  const closeAddressModal = () => setAddressModalData({ isOpen: false, initialData: null });

  const handleSaveAddress = async (data) => {
    setIsSubmittingAddress(true);
    try {
      if (addressModalData.initialData) {
        await axiosInstance.patch(`/api/addresses/${addressModalData.initialData.id}/`, data);
        toast.success('📍 Address updated successfully!');
      } else {
        await axiosInstance.post('/api/addresses/', data);
        toast.success('📍 Address added successfully!');
      }
      const res = await axiosInstance.get('/api/addresses/');
      setAddresses(res.data.results || res.data);
      closeAddressModal();
    } catch (err) { toast.error('❌ Failed to save address'); } 
    finally { setIsSubmittingAddress(false); }
  };

  const handleSetDefaultAddress = async (id) => {
    try {
      await axiosInstance.patch(`/api/addresses/${id}/`, { is_default: true });
      toast.success('⭐ Default address updated!');
      const res = await axiosInstance.get('/api/addresses/');
      setAddresses(res.data.results || res.data);
    } catch (err) { toast.error('❌ Failed to update address'); }
  };

  const promptDeleteAddress = (id) => {
    setAddressToRemove(id);
    setDeleteModalOpen(true);
  };

  const executeDeleteAddress = async () => {
    if (!addressToRemove) return;
    try {
      await axiosInstance.delete(`/api/addresses/${addressToRemove}/`);
      setAddresses(prev => prev.filter(a => a.id !== addressToRemove));
      toast.success('🗑️ Address deleted');
    } catch (err) { 
      toast.error('❌ Failed to delete address'); 
    } finally {
      setDeleteModalOpen(false);
      setAddressToRemove(null);
    }
  };

  return (
    <>
      <AnimatePresence>
        {addressModalData.isOpen && (
          <AddressModal 
            isOpen={addressModalData.isOpen} 
            onClose={closeAddressModal} 
            onSubmit={handleSaveAddress} 
            initialData={addressModalData.initialData} 
            isSubmitting={isSubmittingAddress} 
          />
        )}
      </AnimatePresence>

      {/* --- Wishlist-style Confirmation Modal for Deletion --- */}
      <AnimatePresence>
        {deleteModalOpen && (
          <ModalPortal>
          <Overlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <ModalCard initial={{ scale: 0.95, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.95, opacity: 0, y: 10 }}>
              <ModalIconWrapper>
                <FaExclamationTriangle size={22} />
              </ModalIconWrapper>
              <h3>Delete Address?</h3>
              <p>Are you sure you want to remove this shipping address from your address book?</p>
              <ButtonGroup>
                <ModalSecondaryButton onClick={() => setDeleteModalOpen(false)}>Cancel</ModalSecondaryButton>
                <ModalDangerButton onClick={executeDeleteAddress}>Yes, Remove</ModalDangerButton>
              </ButtonGroup>
            </ModalCard>
          </Overlay>
          </ModalPortal>
        )}
      </AnimatePresence>

      <ProfileCard>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', borderBottom: '1px solid #F1F5F9', paddingBottom: '1rem' }}>
          <h3 style={{ margin: 0, color: '#0F172A', display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '1.2rem', fontWeight: '800' }}>
            <FaMapMarkerAlt color="#0B8457" /> Address Book
          </h3>
          <AddButton onClick={() => openAddressModal()} whileTap={{ scale: 0.97 }}><FaPlus /> Add New</AddButton>
        </div>
        
        <AddressList>
          {addresses.map(addr => (
            <AddressCard key={addr.id} $isDefault={addr.is_default} whileHover={{ y: -2 }} transition={{ duration: 0.2 }}>
              <div className="info">
                <strong>{addr.label} {addr.is_default && <span className="badge">Default</span>}</strong>
                <p>{addr.full_address}</p>
              </div>
              <div className="actions">
                {!addr.is_default && <button className="star" onClick={() => handleSetDefaultAddress(addr.id)} title="Set as Default"><FaStar /></button>}
                <button className="edit" onClick={() => openAddressModal(addr)} title="Edit Address"><FaEdit /></button>
                <button className="delete" onClick={() => promptDeleteAddress(addr.id)} title="Delete Address"><FaTrash /></button>
              </div>
            </AddressCard>
          ))}
          {addresses.length === 0 && <p style={{ color: '#94A3B8', fontStyle: 'italic', textAlign: 'center', padding: '2rem 0' }}>No addresses saved yet.</p>}
        </AddressList>
      </ProfileCard>
    </>
  );
};

export default AddressSection;

// ==========================================
// SAAS LEVEL STYLED COMPONENTS
// ==========================================

const ProfileCard = styled.div` background: #ffffff; border-radius: 24px; padding: 2.2rem; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid rgba(11, 132, 87, 0.08); `;

const AddButton = styled(motion.button)`
  display: flex; align-items: center; gap: 0.5rem; background: #ECFDF5; color: #0B8457; border: 1px solid rgba(16, 185, 129, 0.3); padding: 0.6rem 1.2rem; border-radius: 12px; cursor: pointer; font-weight: 700; font-size: 0.9rem; transition: background 0.2s;
  &:hover { background: #D1FAE5; }
`;

const AddressList = styled.div` display: flex; flex-direction: column; gap: 1rem; `;

const AddressCard = styled(motion.div)`
  display: flex; justify-content: space-between; align-items: flex-start; padding: 1.2rem; border: 2px solid ${props => props.$isDefault ? '#0B8457' : '#E2E8F0'}; border-radius: 16px; background: ${props => props.$isDefault ? 'rgba(11, 132, 87, 0.03)' : '#ffffff'}; transition: all 0.2s;
  .info strong { display: flex; align-items: center; gap: 0.6rem; color: #0F172A; font-weight: 700; } 
  .info p { margin: 0.5rem 0 0 0; color: #475569; font-size: 0.95rem; line-height: 1.5; white-space: pre-wrap; } 
  .badge { background: #0B8457; color: white; font-size: 0.7rem; padding: 0.2rem 0.6rem; border-radius: 50px; text-transform: uppercase; font-weight: 800; } 
  .actions { display: flex; gap: 0.3rem; } 
  .actions button { background: none; border: none; cursor: pointer; padding: 0.6rem; border-radius: 50%; transition: background 0.2s; display: flex; align-items: center; justify-content: center; } 
  .actions .star { color: #F59E0B; &:hover { background: #FEF3C7; } } 
  .actions .edit { color: #0B8457; &:hover { background: #ECFDF5; } } 
  .actions .delete { color: #EF4444; &:hover { background: #FEF2F2; } } 
`;

const FormGroup = styled.div`
  display: flex; flex-direction: column; gap: 0.5rem; text-align: left; width: 100%; box-sizing: border-box; 
  label { font-weight: 700; color: #0F172A; font-size: 0.95rem; } 
  select, textarea { width: 100%; padding: 0.9rem 1.2rem; border-radius: 12px; border: 1px solid #E2E8F0; font-size: 1rem; outline: none; font-family: inherit; box-sizing: border-box; transition: all 0.2s; background: #F8FAFC; color: #0F172A; &:focus { border-color: #0B8457; background: #ffffff; box-shadow: 0 0 0 3px rgba(11, 132, 87, 0.1); } } 
  select { background: #F8FAFC; cursor: pointer; } 
`;

const ModalContentWrapper = styled.div` display: flex; flex-direction: column; gap: 1.2rem; width: 100%; margin-top: 1.5rem; box-sizing: border-box; `;

const Overlay = styled(motion.div)` position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 1rem; `;

const ModalCard = styled(motion.div)`
  position: relative; background: #ffffff; padding: 2.8rem 2.2rem 2.2rem 2.2rem; border-radius: 24px; width: 100%; max-width: 440px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); border: 1px solid rgba(11, 132, 87, 0.1);
  h3 { margin: 0 0 0.6rem 0; color: #0F172A; font-size: 1.5rem; font-weight: 800; } 
  p { color: #64748B; margin: 0 0 2rem 0; font-size: 0.95rem; line-height: 1.5; }
`;

const CloseBtn = styled.button` position: absolute; top: 1.2rem; right: 1.2rem; background: none; border: none; font-size: 1.2rem; color: #94A3B8; cursor: pointer; transition: color 0.2s; &:hover { color: #0F172A; } `;

const ModalIconWrapper = styled.div`
  width: 55px; height: 55px; background: #FEF2F2; color: #DC2626; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.2rem auto;
`;

const ButtonGroup = styled.div` display: flex; gap: 1rem; width: 100%; justify-content: center; box-sizing: border-box; `;

const ModalPrimaryButton = styled(motion.button)`
  flex: 1; padding: 0.9rem 0; border: none; border-radius: 12px; cursor: pointer; background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%); color: white; font-weight: 700; font-size: 1rem; box-shadow: 0 4px 12px rgba(11, 132, 87, 0.25); box-sizing: border-box; 
  &:hover:not(:disabled) { box-shadow: 0 6px 16px rgba(11, 132, 87, 0.35); } 
  &:disabled { opacity: 0.6; cursor: not-allowed; box-shadow: none; } 
`;

const ModalSecondaryButton = styled(motion.button)`
  flex: 1; padding: 0.9rem 0; border: 1px solid #E2E8F0; border-radius: 12px; cursor: pointer; background: #ffffff; color: #475569; font-weight: 700; font-size: 1rem; box-sizing: border-box; 
  &:hover { background: #F8FAFC; color: #0F172A; } 
`;

const ModalDangerButton = styled.button`
  flex: 1; padding: 0.9rem 0; border: none; border-radius: 12px; cursor: pointer; background: #EF4444; color: #ffffff; font-weight: 700; font-size: 0.95rem; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2); transition: all 0.2s;
  &:hover { background: #DC2626; box-shadow: 0 6px 16px rgba(239, 68, 68, 0.3); }
`;