'use client';

import { type ReactNode } from 'react';
import { Drawer } from 'vaul';

interface BottomSheetProps {
  children: ReactNode;
  peekContent: ReactNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function BottomSheet({
  children,
  peekContent,
  open,
  onOpenChange,
}: BottomSheetProps) {
  return (
    <Drawer.Root
      open={open}
      onOpenChange={onOpenChange}
      snapPoints={[60, 0.8]}
      activeSnapPoint={open ? 0.8 : 60}
      modal={true}
    >
      <Drawer.Trigger asChild>
        <button
          className="fixed bottom-0 left-0 right-0 z-40 bg-surface border-t border-border shadow-xl"
          style={{ height: '60px' }}
          onClick={() => onOpenChange(true)}
          aria-label="Rozwiń koszyk"
        >
          <div className="flex flex-col items-center">
            <div className="w-8 h-1 rounded-full bg-border-strong mt-2 mb-2" aria-hidden="true" />
            <div className="w-full px-4 flex items-center">
              {peekContent}
            </div>
          </div>
        </button>
      </Drawer.Trigger>

      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <Drawer.Content
          className="fixed bottom-0 left-0 right-0 z-50 bg-surface border-t border-border rounded-t-lg shadow-xl outline-none"
          style={{ maxHeight: '80vh' }}
        >
          <div className="flex flex-col items-center pt-2 pb-2">
            <div className="w-8 h-1 rounded-full bg-border-strong" aria-hidden="true" />
          </div>

          <Drawer.Title className="sr-only">Koszyk porównania</Drawer.Title>

          <div className="overflow-y-auto overscroll-contain px-4 pb-8" style={{ maxHeight: 'calc(80vh - 24px)' }}>
            {children}
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
