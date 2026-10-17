// src/pages/Dashboard.jsx
import { useEffect, useState, useContext } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import styled from 'styled-components';
import AuthContext from '../context/AuthContext';
import { FaBoxOpen, FaStar, FaUserShield, FaTimes, FaExclamationTriangle } from 'react-icons/fa';
import { toast } from "react-hot-toast";
import {PageHeader,GlowingPageContainer} from '../styles/SharedPageStyles';
import AppLayout from '../components/AppLayout';
import ModalPortal from '../components/ModalPortal';

// Import Modular Sections
import OrdersSection from '../sections/dashboard/OrdersSection';
import ReviewsSection from '../sections/dashboard/ReviewsSection';
import ProfileSection from '../sections/dashboard/ProfileSection';

// Shared Global Modals
const ConfirmationModal = ({ isOpen, onClose, onConfirm, title, message, confirmText, cancelText }) => (
  <AnimatePresence>
    {isOpen && (
      <ModalPortal>
      <Overlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
        <ModalCard initial={{ scale: 0.95, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.95, opacity: 0, y: 10 }}>
          <ModalIconWrapper>
            <FaExclamationTriangle size={24} />
          </ModalIconWrapper>
          
          {/* 🚀 Now it dynamically accepts text based on what action is being taken! */}
          <h3>{title}</h3>
          <p>{message}</p>
          
          <ButtonGroup style={{ marginTop: '1.5rem' }}>
            <ModalSecondaryButton onClick={onClose} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              {cancelText || 'Cancel'}
            </ModalSecondaryButton>
            <ModalDangerButton onClick={onConfirm} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              {confirmText || 'Confirm'}
            </ModalDangerButton>
          </ButtonGroup>
        </ModalCard>
      </Overlay>
      </ModalPortal>
    )}
  </AnimatePresence>
);

const ReviewModal = ({ isOpen, onClose, reviewData, onSubmit, isSubmitting }) => {
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(null);
  const [comment, setComment] = useState('');

  useEffect(() => {
    if (isOpen && reviewData) {
      setRating(reviewData.rating || 0);
      setComment(reviewData.comment || '');
    }
  }, [isOpen, reviewData]);

  if (!isOpen) return null;

  return (
    <ModalPortal>
    <Overlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <ModalCard initial={{ scale: 0.95, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.95, opacity: 0, y: 10 }} style={{ maxWidth: '480px' }}>
        <CloseBtn onClick={onClose}><FaTimes /></CloseBtn>
        <h3>{reviewData.isEditing ? 'Edit Your Review' : 'Leave a Review'}</h3>
        <p style={{ color: '#0B8457', fontWeight: '700', marginBottom: '0.5rem' }}>{reviewData.productName}</p>
        
        {/* 🚀 ADDED A CALL TO ACTION */}
        <RatingLabel>Tap to Rate</RatingLabel>

        <Stars>
          {[...Array(5)].map((_, i) => {
            const starValue = i + 1;
            const isActive = starValue <= (hover || rating);
            return (
              <label key={i}>
                <input type="radio" name="rating" value={starValue} onClick={() => setRating(starValue)} style={{ display: 'none' }} />
                <motion.div whileHover={{ scale: 1.15 }} whileTap={{ scale: 0.9 }}>
                  <FaStar 
                    size={40} /* 🚀 Made stars significantly larger */
                    color={isActive ? '#F59E0B' : '#CBD5E1'} /* 🚀 Darkened empty state for visibility */
                    onMouseEnter={() => setHover(starValue)} 
                    onMouseLeave={() => setHover(null)} 
                    style={{ 
                      cursor: 'pointer', 
                      transition: 'all 200ms ease',
                      filter: isActive ? 'drop-shadow(0 4px 6px rgba(245, 158, 11, 0.4))' : 'none' /* 🚀 Added glow effect */
                    }} 
                  />
                </motion.div>
              </label>
            );
          })}
        </Stars>

        <ModalContentWrapper>
          <textarea 
            placeholder="Share your thoughts about this product..." 
            value={comment} 
            onChange={e => setComment(e.target.value)}
          />

          <ButtonGroup>
            <ModalSecondaryButton onClick={onClose} disabled={isSubmitting}>Cancel</ModalSecondaryButton>
            <ModalPrimaryButton onClick={() => onSubmit({ rating, comment, productId: reviewData.productId, reviewId: reviewData.reviewId })} disabled={isSubmitting || rating === 0 || !comment.trim()}>
              {isSubmitting ? 'Saving...' : 'Submit Review'}
            </ModalPrimaryButton>
          </ButtonGroup>
        </ModalContentWrapper>
      </ModalCard>
    </Overlay>
    </ModalPortal>
  );
};

const Dashboard = () => {
  const { axiosInstance, user } = useContext(AuthContext);
  const [activeTab, setActiveTab] = useState('orders'); 

  const [orders, setOrders] = useState([]);
  const [orderPage, setOrderPage] = useState(1);
  const [totalOrderPages, setTotalOrderPages] = useState(1);

  const [userReviews, setUserReviews] = useState([]);
  const [reviewPage, setReviewPage] = useState(1);
  const [totalReviewPages, setTotalReviewPages] = useState(1);

  const [addresses, setAddresses] = useState([]); 

  const [isLoadingOrders, setIsLoadingOrders] = useState(true);
  const [isLoadingReviews, setIsLoadingReviews] = useState(true);

  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);
  const [orderToCancel, setOrderToCancel] = useState(null);
  const [isDeleteReviewModalOpen, setIsDeleteReviewModalOpen] = useState(false);
  const [reviewToDelete, setReviewToDelete] = useState(null);
  const [reviewModalData, setReviewModalData] = useState({ isOpen: false });
  const [isSubmittingReview, setIsSubmittingReview] = useState(false);

  useEffect(() => {
    const fetchAddresses = async () => {
      try {
        const addressRes = await axiosInstance.get('/api/addresses/');
        setAddresses(addressRes.data.results || addressRes.data);
      } catch (error) { toast.error('Failed to load addresses'); }
    };
    fetchAddresses();
  }, [axiosInstance]);

  const fetchOrders = async () => {
    setIsLoadingOrders(true);
    try {
      const res = await axiosInstance.get(`/api/orders/?page=${orderPage}`);
      setOrders(res.data.results || res.data);
      if (res.data.count) setTotalOrderPages(Math.ceil(res.data.count / 12));
    } catch (error) { toast.error('Failed to load orders'); } 
    finally { setIsLoadingOrders(false); }
  };// eslint-disable-next-line
  useEffect(() => { fetchOrders(); }, [orderPage, axiosInstance]);

  const fetchReviews = async () => {
    if (!user?.id) {
      setIsLoadingReviews(false); // 🚀 Turn off the loader if user isn't loaded yet
      return;
    }

    setIsLoadingReviews(true);
    try {
      const res = await axiosInstance.get(`/api/reviews/?user=${user.id}&page=${reviewPage}`);
      setUserReviews(res.data.results || res.data);
      if (res.data.count) setTotalReviewPages(Math.ceil(res.data.count / 12));
    } catch (error) { 
      toast.error('Failed to load reviews'); 
    } finally { 
      setIsLoadingReviews(false); 
    }
  };
  
  // eslint-disable-next-line
  useEffect(() => { fetchReviews(); }, [reviewPage, axiosInstance, user?.id]);

  const executeCancelOrder = async () => {
    const orderId = orderToCancel;
    setIsCancelModalOpen(false);
    try {
      await axiosInstance.post(`/api/orders/${orderId}/cancel/`);
      setOrders(prev => prev.map(o => o.id === orderId ? { ...o, status: 'cancelled' } : o));
      toast.success(`🛑 Order cancelled successfully!`);
    } catch (error) { toast.error(`❌ Failed to cancel order.`); } 
    finally { setOrderToCancel(null); }
  };

  const handleReviewSubmit = async (data) => {
    setIsSubmittingReview(true);
    try {
      if (reviewModalData.isEditing) {
        await axiosInstance.put(`/api/reviews/${data.reviewId}/`, { product: data.productId, rating: data.rating, comment: data.comment });
        toast.success('✅ Review updated successfully!');
      } else {
        await axiosInstance.post('/api/reviews/', { product: data.productId, rating: data.rating, comment: data.comment });
        toast.success('⭐ Review submitted successfully!');
      }
      fetchReviews(); 
      setReviewModalData({ isOpen: false });
    } catch (err) { toast.error('❌ Failed to save review.'); } 
    finally { setIsSubmittingReview(false); }
  };

  const confirmDeleteReview = (reviewId) => {
      setReviewToDelete(reviewId);
      setIsDeleteReviewModalOpen(true);
    };
  
  const executeDeleteReview = async () => {
      setIsDeleteReviewModalOpen(false);
      try {
        await axiosInstance.delete(`/api/reviews/${reviewToDelete}/`);
        toast.success('🗑️ Review deleted successfully');
        fetchReviews();
      } catch { 
        toast.error('❌ Failed to delete review'); 
      } finally {
        setReviewToDelete(null);
      }
    };

  return (
    <AppLayout>
      <GlowingPageContainer $maxWidth="1100px">
      <AmbientBackground />
      
      {/* 🚀 The Order Cancellation Modal */}
            <ConfirmationModal 
              isOpen={isCancelModalOpen} 
              onClose={() => setIsCancelModalOpen(false)} 
              onConfirm={executeCancelOrder} 
              title="Cancel Order"
              message="Are you sure you want to cancel this order? This will restore item inventory immediately."
              confirmText="Yes, Cancel"
              cancelText="No, Keep it"
            />
      
            {/* 🚀 The NEW Review Deletion Modal */}
            <ConfirmationModal 
              isOpen={isDeleteReviewModalOpen} 
              onClose={() => setIsDeleteReviewModalOpen(false)} 
              onConfirm={executeDeleteReview} 
              title="Delete Review"
              message="Are you sure you want to permanently delete this review? This action cannot be undone."
              confirmText="Yes, Delete"
              cancelText="Cancel"
            />
      
      <AnimatePresence>
        {reviewModalData.isOpen && (
          <ModalPortal>
          <ReviewModal 
            isOpen={reviewModalData.isOpen} 
            onClose={() => setReviewModalData({ isOpen: false })} 
            reviewData={reviewModalData} 
            onSubmit={handleReviewSubmit} 
            isSubmitting={isSubmittingReview} 
          />
          </ModalPortal>
        )}
      </AnimatePresence>
      
      <DashboardContainer>
        <PageHeader initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
          <h1>My Dashboard</h1>
          <p>Manage your orders, product reviews, and account security.</p>
        </PageHeader>

        <TabBar>
          <Tab $active={activeTab === 'orders'} onClick={() => setActiveTab('orders')} whileTap={{ scale: 0.97 }}>
            <FaBoxOpen /> Orders
          </Tab>
          <Tab $active={activeTab === 'reviews'} onClick={() => setActiveTab('reviews')} whileTap={{ scale: 0.97 }}>
            <FaStar /> Reviews
          </Tab>
          <Tab $active={activeTab === 'profile'} onClick={() => setActiveTab('profile')} whileTap={{ scale: 0.97 }}>
            <FaUserShield /> Profile Settings
          </Tab>
        </TabBar>

        <ContentArea>
          {activeTab === 'orders' && (
            <OrdersSection 
              orders={orders}
              isLoadingOrders={isLoadingOrders}
              orderPage={orderPage}
              totalOrderPages={totalOrderPages}
              setOrderPage={setOrderPage}
              userReviews={userReviews}
              openReviewModal={(productInfo, review) => setReviewModalData({ isOpen: true, productId: productInfo.product, productName: productInfo.name || productInfo.product_name, isEditing: !!review, reviewId: review?.id, rating: review?.rating, comment: review?.comment })}
              onCancelOrderClick={(orderId) => { setOrderToCancel(orderId); setIsCancelModalOpen(true); }}
            />
          )}

          {activeTab === 'reviews' && (
            <ReviewsSection 
              userReviews={userReviews}
              isLoadingReviews={isLoadingReviews}
              reviewPage={reviewPage}
              totalReviewPages={totalReviewPages}
              setReviewPage={setReviewPage}
              openReviewModal={(productInfo, review) => setReviewModalData({ isOpen: true, productId: productInfo.product, productName: productInfo.product_name, isEditing: true, reviewId: review?.id, rating: review?.rating, comment: review?.comment })}
              onDeleteReview={confirmDeleteReview}
            />
          )}

          {activeTab === 'profile' && (
            <ProfileSection 
              addresses={addresses} 
              setAddresses={setAddresses} 
            />
          )}
        </ContentArea>
        </DashboardContainer>
      </GlowingPageContainer>
    </AppLayout>
  );
};

export default Dashboard;

// ==========================================
// SAAS LEVEL STYLED COMPONENTS
// ==========================================

const AmbientBackground = styled.div`
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 100%;
  max-width: 1400px;
  height: 600px;
  background: radial-gradient(circle at 50% 10%, rgba(11, 132, 87, 0.08) 0%, transparent 60%);
  pointer-events: none;
  z-index: 0;
`;

const DashboardContainer = styled.div`
  position: relative;
  z-index: 1;
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 1.5rem;
  
  @media (max-width: 768px) {
    padding: 0 1rem;
  }
`;

const TabBar = styled.div`
  display: flex;
  gap: 0.8rem;
  margin-bottom: 2.5rem;
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  padding: 0.5rem;
  border-radius: 50px;
  border: 1px solid rgba(11, 132, 87, 0.12);
  box-shadow: 0 4px 20px rgba(0,0,0,0.02);
  width: fit-content;
  margin-inline: auto;

  /* 🚀 MOBILE FIX: Allow tabs to wrap into multiple rows instead of bleeding off-screen */
  @media (max-width: 768px) {
    width: 100%;
    flex-wrap: wrap;
    justify-content: center;
    border-radius: 24px; /* Slightly squarer to handle stacked rows */
    padding: 0.5rem;
  }
`;

const Tab = styled(motion.button)`
  display: flex;
  align-items: center;
  gap: 0.6rem;
  background: ${props => props.$active ? 'linear-gradient(135deg, #0B8457 0%, #075E3E 100%)' : 'transparent'};
  color: ${props => props.$active ? '#ffffff' : '#64748B'};
  border: none;
  padding: 0.7rem 1.6rem;
  border-radius: 50px;
  font-weight: 700;
  font-size: 0.95rem;
  cursor: pointer;
  transition: color 0.2s;
  white-space: nowrap;
  box-shadow: ${props => props.$active ? '0 4px 14px rgba(11, 132, 87, 0.25)' : 'none'};

  &:hover {
    color: ${props => props.$active ? '#ffffff' : '#0F172A'};
  }

  /* 🚀 MOBILE FIX: Dynamically resize tabs to fill the available space */
  @media (max-width: 768px) {
    padding: 0.6rem 1rem;
    font-size: 0.85rem;
    flex: 1 1 auto; 
    justify-content: center;
  }
`;

const ContentArea = styled.div`
  min-height: 400px;
`;

// Shared Modals
const Overlay = styled(motion.div)`
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 1rem;
`;

const ModalCard = styled(motion.div)`
  position: relative; background: #ffffff; padding: 2.5rem; border-radius: 24px; width: 100%; max-width: 440px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); border: 1px solid rgba(11, 132, 87, 0.1);
  h3 { margin: 0 0 0.5rem 0; color: #0F172A; font-size: 1.5rem; font-weight: 800; } 
  p { color: #64748B; margin-bottom: 0; font-size: 1rem; line-height: 1.5; }
`;

const ModalIconWrapper = styled.div`
  width: 60px; height: 60px; background: #FEF2F2; color: #EF4444; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem auto;
`;

const CloseBtn = styled.button`
  position: absolute; top: 1.2rem; right: 1.2rem; background: none; border: none; font-size: 1.2rem; color: #94A3B8; cursor: pointer; transition: color 0.2s;
  &:hover { color: #0F172A; } 
`;

const ModalContentWrapper = styled.div`
  display: flex; flex-direction: column; gap: 1.2rem; width: 100%; margin-top: 1.5rem; box-sizing: border-box; 
  textarea { width: 100%; height: 110px; padding: 0.9rem 1rem; border-radius: 12px; border: 1px solid #E2E8F0; font-size: 1rem; outline: none; font-family: inherit; box-sizing: border-box; resize: none; transition: all 0.2s; color: #0F172A; background: #F8FAFC; &:focus { border-color: #0B8457; background: #ffffff; box-shadow: 0 0 0 3px rgba(11, 132, 87, 0.1); } } 
`;

const ButtonGroup = styled.div` display: flex; gap: 1rem; width: 100%; justify-content: center; box-sizing: border-box; `;

const RatingLabel = styled.div`
  font-size: 0.85rem;
  text-transform: uppercase;
  font-weight: 800;
  color: #94A3B8;
  letter-spacing: 1px;
  margin-top: 1rem;
`;

const Stars = styled.div` 
  display: flex; 
  justify-content: center; 
  align-items: center;
  margin: 0.5rem 0 1.5rem 0; 
  gap: 12px; 
  
  /* 🚀 Added a soft grey container background to force the stars to pop */
  background: #F8FAFC; 
  padding: 1rem;
  border-radius: 16px;
  border: 1px dashed #CBD5E1;
`;

const ModalPrimaryButton = styled(motion.button)`
  flex: 1; padding: 0.9rem 0; border: none; border-radius: 12px; cursor: pointer; background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%); color: white; font-weight: 700; font-size: 1rem; box-shadow: 0 4px 12px rgba(11, 132, 87, 0.25); box-sizing: border-box; 
  &:hover:not(:disabled) { box-shadow: 0 6px 16px rgba(11, 132, 87, 0.35); } 
  &:disabled { opacity: 0.6; cursor: not-allowed; box-shadow: none; } 
`;

const ModalDangerButton = styled(motion.button)`
  flex: 1; padding: 0.9rem 0; border: none; border-radius: 12px; cursor: pointer; background: #EF4444; color: white; font-weight: 700; font-size: 1rem; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2); box-sizing: border-box; 
  &:hover { background: #DC2626; box-shadow: 0 6px 16px rgba(239, 68, 68, 0.3); } 
`;

const ModalSecondaryButton = styled(motion.button)`
  flex: 1; padding: 0.9rem 0; border: 1px solid #E2E8F0; border-radius: 12px; cursor: pointer; background: #ffffff; color: #475569; font-weight: 700; font-size: 1rem; box-sizing: border-box; 
  &:hover { background: #F8FAFC; color: #0F172A; } 
`;