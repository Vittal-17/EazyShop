import styled, { keyframes } from 'styled-components';

// 🚀 The Universal Shimmer Animation
const shimmer = keyframes`
  0% { background-position: -1000px 0; }
  100% { background-position: 1000px 0; }
`;

const SkeletonBase = styled.div`
  /* 🚀 Changed to deeper grays so it pops against the white cards */
  background: #e8f5e9; 
  background-image: linear-gradient(90deg, #e8f5e9 0px, #c8e6c9 40px, #e8f5e9 80px);
  
  background-size: 1000px 100%;
  animation: ${shimmer} 2s infinite linear;
  border-radius: ${props => props.$borderRadius || '8px'};
  width: ${props => props.$width || '100%'};
  height: ${props => props.$height || '20px'};
  margin-bottom: ${props => props.$mb || '0'};
`;

// ==========================================
// SHAPE 1: Product Card Skeleton
// ==========================================
const CardWrapper = styled.div`
  background: white;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 15px rgba(0,0,0,0.03);
  border: 1px solid #f1f5f9;
  display: flex;
  flex-direction: column;
  height: 100%;
`;

const DetailsWrapper = styled.div`
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  flex: 1;
`;

export const SkeletonProductCard = () => (
  <CardWrapper>
    <SkeletonBase $height="200px" $borderRadius="0" />
    <DetailsWrapper>
      <SkeletonBase $height="24px" $mb="1rem" $width="80%" />
      <SkeletonBase $height="20px" $mb="0.5rem" $width="40%" />
      <SkeletonBase $height="16px" $mb="1.5rem" $width="60%" />
      <div style={{ marginTop: 'auto', display: 'flex', gap: '0.5rem' }}>
        <SkeletonBase $height="40px" $borderRadius="8px" />
      </div>
    </DetailsWrapper>
  </CardWrapper>
);

// ==========================================
// SHAPE 2: Standard Row/List Skeleton (For Orders/Cart)
// ==========================================
const RowWrapper = styled.div`
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 1rem;
  background: white;
  border-radius: 12px;
  border: 1px solid #f1f5f9;
  margin-bottom: 1rem;
`;

export const SkeletonRow = () => (
  <RowWrapper>
    <SkeletonBase $width="80px" $height="80px" $borderRadius="8px" />
    <div style={{ flex: 1 }}>
      <SkeletonBase $height="20px" $mb="0.5rem" $width="40%" />
      <SkeletonBase $height="16px" $width="25%" />
    </div>
    <SkeletonBase $width="100px" $height="40px" $borderRadius="8px" />
  </RowWrapper>
);