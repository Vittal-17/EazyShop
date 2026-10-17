// src/sections/ReviewsSection.jsx
import { useState, useEffect, useContext } from 'react';
import styled from 'styled-components';
import { motion, AnimatePresence } from 'framer-motion';
import { FaStar, FaTrash } from 'react-icons/fa';
import AuthContext from '../context/AuthContext';
import { toast } from "react-hot-toast";
import ModalPortal from '../components/ModalPortal';

const ReviewsSection = () => {
  const { axiosInstance } = useContext(AuthContext);
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);

  // Pagination State
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [reviewToDelete, setReviewToDelete] = useState(null);

  const fetchReviews = async () => {
    try {
      setLoading(true);
      const res = await axiosInstance.get(`/api/reviews/?page=${currentPage}`);
      setReviews(res.data.results || res.data);
      if (res.data.count) setTotalPages(Math.ceil(res.data.count / 12));
    } catch (err) { toast.error('❌ Failed to load reviews'); } 
    finally { setLoading(false); }
  };

  useEffect(() => {
    fetchReviews();
    // eslint-disable-next-line
  }, [currentPage]);

  const executeDelete = async () => {
    if (!reviewToDelete) return;
    try {
      await axiosInstance.delete(`/api/reviews/${reviewToDelete}/`);
      toast.success('🗑️ Review deleted');
      fetchReviews();
    } catch { toast.error('❌ Failed to delete review'); } 
    finally { setIsDeleteModalOpen(false); setReviewToDelete(null); }
  };

  const renderStars = (rating) => {
    const validRating = rating || 5; 
    return [...Array(5)].map((_, i) => <FaStar key={i} color={i < validRating ? "#F59E0B" : "#E2E8F0"} />);
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <SectionTitle>⭐ Customer Reviews</SectionTitle>
      
      {loading ? (
        <LoadingWrapper><Spinner /><LoadingText>Loading reviews...</LoadingText></LoadingWrapper>
      ) : reviews.length === 0 ? (
        <EmptyState><span className="emoji">💬</span><h3>No reviews found</h3><p>No customer reviews have been posted yet.</p></EmptyState>
      ) : (
        <ul style={{ padding: 0, listStyle: 'none' }}>
          {reviews.map(review => (
            <ListItem key={review.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} whileHover={{ y: -2 }}>
              <ReviewDetails>
                <div style={{ fontWeight: '800', fontSize: '1.15rem', color: '#0F172A' }}>
                  {review.username || 'Anonymous User'} <span style={{ color: '#64748B', fontWeight: '500', fontSize: '0.95rem' }}> on </span>
                  <span style={{ color: '#0B8457' }}>{review.product_name || 'Product'}</span>
                </div>
                <StarsContainer>{renderStars(review.rating)}</StarsContainer>
                <div style={{ fontStyle: 'italic', color: '#475569', marginTop: '0.5rem', lineHeight: '1.6', fontSize: '1rem' }}>"{review.comment}"</div>
              </ReviewDetails>
              <DeleteButton onClick={() => { setReviewToDelete(review.id); setIsDeleteModalOpen(true); }} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
                <FaTrash /> Delete
              </DeleteButton>
            </ListItem>
          ))}
        </ul>
      )}

      {totalPages > 1 && (
        <PaginationWrapper>
          <PageButton onClick={() => setCurrentPage(p => Math.max(p - 1, 1))} disabled={currentPage === 1}>&larr; Prev</PageButton>
          <PageInfo>Page {currentPage} of {totalPages}</PageInfo>
          <PageButton onClick={() => setCurrentPage(p => Math.min(p + 1, totalPages))} disabled={currentPage === totalPages}>Next &rarr;</PageButton>
        </PaginationWrapper>
      )}

      <AnimatePresence>
        {isDeleteModalOpen && (
          <ModalPortal>
          <ConfirmOverlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <ConfirmCard initial={{ scale: 0.9, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.9, opacity: 0, y: 10 }}>
              <h3>Delete Review</h3>
              <p>Are you sure you want to delete this review? It cannot be recovered.</p>
              <ButtonGroup>
                <CancelBtn onClick={() => setIsDeleteModalOpen(false)}>Cancel</CancelBtn>
                <ConfirmDeleteBtn onClick={executeDelete}>Yes, Delete</ConfirmDeleteBtn>
              </ButtonGroup>
            </ConfirmCard>
          </ConfirmOverlay>
          </ModalPortal>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default ReviewsSection;

// STYLED COMPONENTS
const SectionTitle = styled.h2` color: #0F172A; margin-bottom: 1.5rem; font-size: 1.5rem; font-weight: 800; `;

const LoadingWrapper = styled.div` display: flex; flex-direction: column; align-items: center; justify-content: center; margin-top: 4rem; `;
const Spinner = styled.div` width: 45px; height: 45px; border: 4px solid #E2E8F0; border-top: 4px solid #0B8457; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 1rem; @keyframes spin { to { transform: rotate(360deg); } } `;
const LoadingText = styled.div` font-size: 1.1rem; font-weight: 600; color: #0B8457; `;

const EmptyState = styled(motion.div)`
  text-align: center; padding: 5rem 2rem; background: #ffffff; border-radius: 24px; border: 1px dashed #CBD5E1;
  .emoji { font-size: 3.5rem; display: block; margin-bottom: 1rem; }
  h3 { color: #0F172A; font-size: 1.5rem; font-weight: 800; margin-bottom: 0.5rem; }
  p { color: #64748B; font-size: 1rem; }
`;

const ListItem = styled(motion.li)` background: #ffffff; padding: 1.8rem; border-radius: 20px; margin-bottom: 1rem; display: flex; flex-direction: column; gap: 1rem; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid rgba(11, 132, 87, 0.08); @media (min-width: 768px) { flex-direction: row; justify-content: space-between; align-items: center; } `;
const ReviewDetails = styled.div` flex: 1; min-width: 0; `;
const StarsContainer = styled.div` display: flex; gap: 0.3rem; color: #F59E0B; margin-top: 0.4rem; font-size: 1.1rem; `;

const DeleteButton = styled(motion.button)` 
  padding: 0.6rem 1.2rem; background: #FEF2F2; color: #DC2626; border: 1px solid #FCA5A5; border-radius: 12px; font-size: 0.9rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 0.4rem; white-space: nowrap; 
  &:hover { background: #FEE2E2; } 
`;

const PaginationWrapper = styled.div` display: flex; justify-content: center; align-items: center; gap: 1rem; margin-top: 3rem; padding-bottom: 1rem; `;
const PageButton = styled.button` padding: 0.6rem 1.4rem; border-radius: 50px; border: none; font-weight: 700; background: ${props => props.disabled ? '#F1F5F9' : '#0B8457'}; color: ${props => props.disabled ? '#94A3B8' : 'white'}; cursor: ${props => props.disabled ? 'not-allowed' : 'pointer'}; transition: 0.2s; box-shadow: ${props => props.disabled ? 'none' : '0 4px 10px rgba(11, 132, 87, 0.2)'}; &:hover:not(:disabled) { background: #086341; transform: translateY(-1px); } `;
const PageInfo = styled.span` font-weight: 700; color: #334155; font-size: 0.95rem; background: #ffffff; padding: 0.6rem 1.2rem; border-radius: 50px; border: 1px solid #E2E8F0; `;

const ConfirmOverlay = styled(motion.div)` position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 10000; padding: 1rem; `;
const ConfirmCard = styled(motion.div)` background: white; padding: 2.5rem; border-radius: 24px; width: 100%; max-width: 420px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); h3 { margin-top: 0; color: #0F172A; font-weight: 800; } p { color: #64748B; margin-bottom: 2rem; line-height: 1.5; } `;
const ButtonGroup = styled.div` display: flex; gap: 1rem; justify-content: center; `;
const ConfirmDeleteBtn = styled.button` padding: 0.9rem 1.5rem; border: none; border-radius: 12px; cursor: pointer; font-weight: 700; background: #EF4444; color: #ffffff; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2); &:hover { background: #DC2626; } `;
const CancelBtn = styled.button` padding: 0.9rem 1.5rem; border: 1px solid #E2E8F0; border-radius: 12px; cursor: pointer; font-weight: 700; background: #ffffff; color: #475569; &:hover { background: #F8FAFC; color: #0F172A; } `;