'use client';

import { useState } from 'react';
import Modal from '@/components/ui/Modal';
import Button from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { apiClient } from '@/lib/api-client';
import type { FeedbackRequest } from '@/generated/api-types';

interface FeedbackModalProps {
  open: boolean;
  onClose: () => void;
  restaurantId: string;
  itemId?: string;
}

type FeedbackType = 'wrong_price' | 'wrong_match' | 'other';

const FEEDBACK_OPTIONS: { value: FeedbackType; label: string }[] = [
  { value: 'wrong_price', label: 'Nieprawidłowa cena' },
  { value: 'wrong_match', label: 'To nie ta sama restauracja' },
  { value: 'other', label: 'Inne' },
];

export default function FeedbackModal({
  open,
  onClose,
  restaurantId,
  itemId,
}: FeedbackModalProps) {
  const [feedbackType, setFeedbackType] = useState<FeedbackType | null>(null);
  const [description, setDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { addToast } = useToast();

  const handleSubmit = async () => {
    if (!feedbackType) return;

    setIsSubmitting(true);

    try {
      const payload: FeedbackRequest = {
        feedback_type: feedbackType,
        canonical_restaurant_id: restaurantId,
        platform_menu_item_id: itemId,
        description: description.trim() || undefined,
        context_snapshot: {},
      };

      await apiClient.submitFeedback(payload);
      addToast('Dziękujemy za zgłoszenie!', 'success');
      handleClose();
    } catch {
      addToast('Nie udało się wysłać zgłoszenia. Spróbuj ponownie.', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setFeedbackType(null);
    setDescription('');
    onClose();
  };

  return (
    <Modal open={open} onClose={handleClose} title="Zgłoś problem">
      <div className="flex flex-col gap-4">
        {/* Type selection */}
        <fieldset>
          <legend className="text-sm font-medium text-text-primary mb-2">
            Co jest nie tak?
          </legend>
          <div className="flex flex-col gap-2">
            {FEEDBACK_OPTIONS.map((option) => (
              <label
                key={option.value}
                className="flex items-center gap-2.5 py-1.5 px-2 rounded-sm cursor-pointer hover:bg-bg transition-colors duration-fast"
              >
                <input
                  type="radio"
                  name="feedback-type"
                  value={option.value}
                  checked={feedbackType === option.value}
                  onChange={() => setFeedbackType(option.value)}
                  className="accent-primary"
                />
                <span className="text-sm text-text-primary">{option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {/* Description */}
        <div>
          <label
            htmlFor="feedback-desc"
            className="block text-sm font-medium text-text-primary mb-1.5"
          >
            Szczegóły (opcjonalnie):
          </label>
          <textarea
            id="feedback-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="w-full px-3 py-2 text-sm bg-surface border border-border rounded-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors duration-fast resize-none"
            placeholder="Opisz problem..."
          />
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-2 pt-2">
          <Button variant="ghost" size="sm" onClick={handleClose}>
            Anuluj
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleSubmit}
            loading={isSubmitting}
            disabled={!feedbackType}
          >
            Wyślij
          </Button>
        </div>
      </div>
    </Modal>
  );
}
