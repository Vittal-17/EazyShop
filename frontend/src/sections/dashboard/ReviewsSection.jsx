// src/sections/dashboard/ReviewsSection.jsx
import { motion } from 'framer-motion';
import styled from 'styled-components';
import { FaStar, FaEdit, FaTrash } from 'react-icons/fa';

const ReviewsSection = ({ userReviews, isLoadingReviews, reviewPage, totalReviewPages, setReviewPage, openReviewModal, onDeleteReview }) => {
  if (isLoadingReviews) {
    return <LoadingWrapper><Spinner /><LoadingText>Loading reviews...</LoadingText></LoadingWrapper>;
  }

  if (userReviews.length === 0) {
    return (
      <EmptyState initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
        <span className="emoji">⭐</span>
        <h3>No reviews yet</h3>
        <p>You haven't reviewed any products yet.</p>
      </EmptyState>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <ReviewsList>
        {userReviews.map(review => (
          <ReviewItemCard key={review.id} whileHover={{ y: -2 }} transition={{ duration: 0.2 }}>
            <ReviewContent>
              <h4>{review.product_name || `Product ID: ${review.product}`}</h4>
              <div className="stars">
                {[...Array(5)].map((_, i) => <FaStar key={i} size={15} color={i < review.rating ? '#F59E0B' : '#E2E8F0'} />)}
              </div>
              <p className="comment">"{review.comment}"</p>
            </ReviewContent>
            <ReviewActions>
              <ModalSecondaryButton onClick={() => openReviewModal({ product: review.product, product_name: review.product_name }, review)} whileTap={{ scale: 0.97 }}>
                <FaEdit /> Edit
              </ModalSecondaryButton>
              <ModalDangerButton onClick={() => onDeleteReview(review.id)} whileTap={{ scale: 0.97 }}>
                <FaTrash /> Delete
              </ModalDangerButton>
            </ReviewActions>
          </ReviewItemCard>
        ))}
      </ReviewsList>

      {totalReviewPages > 1 && (
        <PaginationWrapper>
          <PageButton onClick={() => setReviewPage(p => Math.max(p - 1, 1))} disabled={reviewPage === 1}>&larr; Prev</PageButton>
          <PageInfo>Page {reviewPage} of {totalReviewPages}</PageInfo>
          <PageButton onClick={() => setReviewPage(p => Math.min(p + 1, totalReviewPages))} disabled={reviewPage === totalReviewPages}>Next &rarr;</PageButton>
        </PaginationWrapper>
      )}
    </motion.div>
  );
};

export default ReviewsSection;

// ==========================================
// SAAS LEVEL STYLED COMPONENTS
// ==========================================

const LoadingWrapper = styled.div` display: flex; flex-direction: column; align-items: center; justify-content: center; margin-top: 4rem; `;
const Spinner = styled.div` width: 45px; height: 45px; border: 4px solid #E2E8F0; border-top: 4px solid #0B8457; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 1rem; @keyframes spin { to { transform: rotate(360deg); } } `;
const LoadingText = styled.div` font-size: 1.1rem; font-weight: 600; color: #0B8457; `;

const EmptyState = styled(motion.div)`
  text-align: center; padding: 5rem 2rem; background: #ffffff; border-radius: 24px; border: 1px dashed #CBD5E1;
  .emoji { font-size: 3.5rem; display: block; margin-bottom: 1rem; }
  h3 { color: #0F172A; font-size: 1.5rem; font-weight: 800; margin-bottom: 0.5rem; }
  p { color: #64748B; font-size: 1rem; }
`;

const ReviewsList = styled.ul` display: flex; flex-direction: column; gap: 1.5rem; list-style: none; padding: 0; `;

const ReviewItemCard = styled(motion.li)`
  background: #ffffff; border-radius: 24px; padding: 1.8rem; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid rgba(11, 132, 87, 0.08); display: flex; flex-direction: column; gap: 1.5rem; 
  @media (min-width: 600px) { flex-direction: row; justify-content: space-between; align-items: flex-start; }
`;

const ReviewContent = styled.div`
  flex: 1; min-width: 0;
  h4 { margin: 0 0 0.5rem 0; color: #0F172A; font-size: 1.15rem; font-weight: 800; }
  .stars { display: flex; gap: 4px; margin-bottom: 0.8rem; }
  .comment { margin: 0; color: #475569; font-style: italic; font-size: 1rem; line-height: 1.6; }
`;

const ReviewActions = styled.div` display: flex; gap: 0.8rem; align-items: flex-start; white-space: nowrap; `;

const ModalDangerButton = styled(motion.button)`
  padding: 0.6rem 1.2rem; border: none; border-radius: 12px; cursor: pointer; background: #FEF2F2; color: #DC2626; border: 1px solid #FCA5A5; font-weight: 700; font-size: 0.9rem; display: flex; align-items: center; gap: 0.4rem; transition: background 0.2s;
  &:hover { background: #FEE2E2; }
`;

const ModalSecondaryButton = styled(motion.button)`
  padding: 0.6rem 1.2rem; border: 1px solid #E2E8F0; border-radius: 12px; cursor: pointer; background: #ffffff; color: #334155; font-weight: 700; font-size: 0.9rem; display: flex; align-items: center; gap: 0.4rem; transition: background 0.2s;
  &:hover { background: #F8FAFC; color: #0F172A; }
`;

const PaginationWrapper = styled.div` display: flex; justify-content: center; align-items: center; gap: 1rem; margin-top: 3rem; padding-bottom: 1rem; `;
const PageButton = styled.button` padding: 0.6rem 1.4rem; border-radius: 50px; border: none; font-weight: 700; background: ${props => props.disabled ? '#F1F5F9' : '#0B8457'}; color: ${props => props.disabled ? '#94A3B8' : 'white'}; cursor: ${props => props.disabled ? 'not-allowed' : 'pointer'}; transition: 0.2s; box-shadow: ${props => props.disabled ? 'none' : '0 4px 10px rgba(11, 132, 87, 0.2)'}; &:hover:not(:disabled) { background: #086341; transform: translateY(-1px); } `;
const PageInfo = styled.span` font-weight: 700; color: #334155; font-size: 0.95rem; background: #ffffff; padding: 0.6rem 1.2rem; border-radius: 50px; border: 1px solid #E2E8F0; `;