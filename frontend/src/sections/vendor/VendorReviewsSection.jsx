// src/sections/vendor/VendorReviewsSection.jsx
import { useState, useContext, useEffect } from 'react';
import styled from 'styled-components';
import { motion } from 'framer-motion';
import { FaStar, FaBox } from 'react-icons/fa';
import { toast } from 'react-hot-toast';
import AuthContext from '../../context/AuthContext';

const VendorReviewsSection = () => {
  const { axiosInstance } = useContext(AuthContext);
  const [reviews, setReviews] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchVendorReviews = async () => {
      setIsLoading(true);
      try {
        const res = await axiosInstance.get('/api/reviews/');
        setReviews(res.data.results || res.data);
      } catch (error) {
        toast.error('❌ Failed to load product reviews.');
      } finally {
        setIsLoading(false);
      }
    };
    fetchVendorReviews();
  }, [axiosInstance]);

  const renderStars = (rating) => {
    const validRating = rating || 5;
    return [...Array(5)].map((_, i) => (
      <FaStar key={i} size={15} color={i < validRating ? '#F59E0B' : '#E2E8F0'} />
    ));
  };

  if (isLoading) {
    return <LoadingWrapper><Spinner /><LoadingText>Loading Reviews...</LoadingText></LoadingWrapper>;
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <SectionHeader>
        <div>
          <h2>Customer Feedback</h2>
          <p>Monitor buyer ratings and reviews for your marketplace catalog.</p>
        </div>
      </SectionHeader>

      {reviews.length === 0 ? (
        <EmptyState>
          <span className="emoji">💬</span>
          <h3>No reviews yet</h3>
          <p>Once customers purchase and review your products, their feedback will appear here.</p>
        </EmptyState>
      ) : (
        <ReviewsList>
          {reviews.map((review) => (
            <ReviewCard key={review.id} whileHover={{ y: -2 }} transition={{ duration: 0.2 }}>
              <div className="review-header">
                <div className="product-title">
                  <FaBox color="#0B8457" /> <strong>{review.product_name || 'Product Item'}</strong>
                </div>
                <div className="stars">{renderStars(review.rating)}</div>
              </div>
              <p className="comment">"{review.comment}"</p>
              <div className="review-footer">
                <span>Reviewed by <strong>{review.username || 'Verified Buyer'}</strong></span>
                <span className="date">{review.created_at ? new Date(review.created_at).toLocaleDateString() : ''}</span>
              </div>
            </ReviewCard>
          ))}
        </ReviewsList>
      )}
    </motion.div>
  );
};

export default VendorReviewsSection;

// ==========================================
// SAAS LEVEL STYLED COMPONENTS
// ==========================================

const LoadingWrapper = styled.div` display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 4rem 0; `;
const Spinner = styled.div` width: 45px; height: 45px; border: 4px solid #E2E8F0; border-top: 4px solid #0B8457; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 1rem; @keyframes spin { to { transform: rotate(360deg); } } `;
const LoadingText = styled.div` font-size: 1.1rem; font-weight: 600; color: #0B8457; `;

const SectionHeader = styled.div` 
  background: #ffffff; padding: 1.8rem 2.2rem; border-radius: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid rgba(11, 132, 87, 0.08); margin-bottom: 2rem;
  h2 { margin: 0 0 0.3rem 0; color: #0F172A; font-size: 1.4rem; font-weight: 800; }
  p { margin: 0; color: #64748B; font-size: 0.95rem; }
`;

const EmptyState = styled.div` 
  text-align: center; padding: 5rem 2rem; background: #ffffff; border-radius: 24px; border: 1px dashed #CBD5E1; 
  .emoji { font-size: 3.5rem; display: block; margin-bottom: 1rem; }
  h3 { color: #0F172A; font-size: 1.5rem; font-weight: 800; margin-bottom: 0.5rem; }
  p { color: #64748B; font-size: 1rem; } 
`;

const ReviewsList = styled.div` display: flex; flex-direction: column; gap: 1.5rem; `;

const ReviewCard = styled(motion.div)`
  background: white; border-radius: 20px; padding: 1.8rem; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid rgba(11, 132, 87, 0.08);
  
  .review-header {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem;
    .product-title { display: flex; align-items: center; gap: 0.5rem; color: #0F172A; font-size: 1.1rem; font-weight: 700; }
    .stars { display: flex; gap: 4px; }
  }

  .comment {
    color: #475569; font-style: italic; font-size: 1rem; line-height: 1.6; margin: 0 0 1.2rem 0;
  }

  .review-footer {
    display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; color: #64748B; border-top: 1px solid #F1F5F9; padding-top: 0.8rem;
    strong { color: #0F172A; }
    .date { color: #94A3B8; }
  }
`;