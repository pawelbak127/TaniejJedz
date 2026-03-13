'use client';

import { useState } from 'react';
import FeedbackModal from './FeedbackModal';

interface FeedbackButtonProps {
  restaurantId: string;
  itemId?: string;
}

export default function FeedbackButton({ restaurantId, itemId }: FeedbackButtonProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="text-xs text-text-tertiary hover:text-text-secondary hover:underline transition-colors duration-fast"
      >
        Zgłoś błąd
      </button>

      <FeedbackModal
        open={isOpen}
        onClose={() => setIsOpen(false)}
        restaurantId={restaurantId}
        itemId={itemId}
      />
    </>
  );
}
