import { MapPin, Search, ArrowRightLeft } from 'lucide-react';
import Header from '@/components/shared/Header';
import Footer from '@/components/shared/Footer';
import AddressInput from '@/components/address/AddressInput';

export default function HomePage() {
  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 flex flex-col">
        {/* Hero */}
        <section className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 py-16 sm:py-24">
          <div className="w-full max-w-xl text-center">
            <h1 className="text-3xl sm:text-[2.4rem] font-semibold text-text-primary leading-tight tracking-tight">
              Porównaj ceny dostaw jedzenia{' '}
              <span className="text-primary">w Twojej okolicy</span>
            </h1>

            <p className="mt-4 text-lg text-text-secondary leading-relaxed">
              Sprawdzamy Pyszne.pl, Uber Eats, Wolt i Glovo — żebyś płacił mniej.
            </p>

            <div className="mt-8">
              <AddressInput autoFocus size="large" />
            </div>

            <p className="mt-4 text-sm text-text-tertiary">
              Obsługujemy:{' '}
              <span className="font-medium text-text-secondary">Warszawa</span>
              <span className="mx-1.5">&middot;</span>
              Kraków, Wrocław — wkrótce
            </p>
          </div>
        </section>

        {/* How it works */}
        <section className="border-t border-border bg-surface px-4 sm:px-6 py-16">
          <div className="mx-auto max-w-3xl">
            <h2 className="text-center text-xl font-semibold text-text-primary mb-10">
              Jak to działa?
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 sm:gap-6">
              <Step
                number={1}
                icon={<MapPin size={22} />}
                title="Wpisz adres dostawy"
                description="Podaj adres, a my znajdziemy restauracje w Twojej okolicy na wszystkich platformach."
              />
              <Step
                number={2}
                icon={<Search size={22} />}
                title="Wybierz i porównaj ceny"
                description="Przeglądaj zunifikowane menu z cenami z każdej platformy obok siebie."
              />
              <Step
                number={3}
                icon={<ArrowRightLeft size={22} />}
                title="Zaoszczędź na zamówieniu"
                description="Dodaj produkty do koszyka, a my policzymy, gdzie zapłacisz najmniej — z dostawą i promocjami."
              />
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}

function Step({
  number,
  icon,
  title,
  description,
}: {
  number: number;
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center text-center">
      <div
        className="w-12 h-12 rounded-full bg-primary-light text-primary flex items-center justify-center mb-4"
        aria-hidden="true"
      >
        {icon}
      </div>
      <div className="text-xs font-medium tracking-[0.05em] uppercase text-text-tertiary mb-1.5">
        Krok {number}
      </div>
      <h3 className="text-base font-semibold text-text-primary mb-2">
        {title}
      </h3>
      <p className="text-sm text-text-secondary leading-relaxed max-w-[260px]">
        {description}
      </p>
    </div>
  );
}
