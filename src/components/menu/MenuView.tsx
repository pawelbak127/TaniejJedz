'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import type { MenuCategory } from '@/generated/api-types';
import MenuItemRow from './MenuItemRow';

interface MenuViewProps {
  categories: MenuCategory[];
  restaurantId: string;
}

export default function MenuView({ categories, restaurantId }: MenuViewProps) {
  const [activeCategory, setActiveCategory] = useState(0);
  const categoryRefs = useRef<(HTMLElement | null)[]>([]);
  const tabsRef = useRef<HTMLDivElement>(null);
  const isScrollingRef = useRef(false);

  const scrollToCategory = useCallback((index: number) => {
    isScrollingRef.current = true;
    setActiveCategory(index);
    const el = categoryRefs.current[index];
    if (el) {
      const offset = (tabsRef.current?.getBoundingClientRect().height || 48) + 16;
      const top = el.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({ top, behavior: 'smooth' });
      setTimeout(() => {
        isScrollingRef.current = false;
      }, 500);
    }
  }, []);

  useEffect(() => {
    const handleScroll = () => {
      if (isScrollingRef.current) return;
      const offset = (tabsRef.current?.getBoundingClientRect().height || 48) + 32;
      for (let i = categoryRefs.current.length - 1; i >= 0; i--) {
        const el = categoryRefs.current[i];
        if (el) {
          const rect = el.getBoundingClientRect();
          if (rect.top <= offset) {
            setActiveCategory(i);
            return;
          }
        }
      }
      setActiveCategory(0);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Scroll active tab into view
  useEffect(() => {
    if (!tabsRef.current) return;
    const nav = tabsRef.current.querySelector('nav');
    if (!nav) return;
    const activeBtn = nav.children[activeCategory] as HTMLElement | undefined;
    activeBtn?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
  }, [activeCategory]);

  return (
    <div>
      {/* Sticky category tabs */}
      <div
        ref={tabsRef}
        className="sticky top-0 z-10 bg-surface border-b border-border -mx-4 px-4 lg:-mx-0 lg:px-0"
      >
        <nav
          className="flex items-center gap-1 overflow-x-auto scrollbar-hide py-2"
          role="tablist"
          aria-label="Kategorie menu"
        >
          {categories.map((cat, index) => (
            <button
              key={cat.name}
              role="tab"
              aria-selected={activeCategory === index}
              onClick={() => scrollToCategory(index)}
              className={[
                'shrink-0 px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap',
                'transition-colors duration-fast min-h-[36px]',
                activeCategory === index
                  ? 'bg-primary text-text-inverse'
                  : 'text-text-secondary hover:bg-bg',
              ].join(' ')}
            >
              {cat.name}
            </button>
          ))}
        </nav>
      </div>

      {/* Category sections */}
      {categories.map((category, index) => (
        <section
          key={category.name}
          ref={(el) => { categoryRefs.current[index] = el; }}
          className="mt-6"
          aria-labelledby={`cat-${index}`}
        >
          <h3
            id={`cat-${index}`}
            className="text-xs font-semibold uppercase tracking-[0.05em] text-text-tertiary mb-3"
          >
            {category.name}
          </h3>
          <div>
            {category.items.map((item, itemIndex) => (
              <div
                key={item.id}
                className="animate-fade-in-up"
                style={{ animationDelay: `${itemIndex * 50}ms` }}
              >
                <MenuItemRow
                  item={item}
                  restaurantId={restaurantId}
                />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
