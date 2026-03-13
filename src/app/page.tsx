export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center">
      <h1
        className="text-4xl font-semibold"
        style={{ color: 'var(--color-text-primary)' }}
      >
        TaniejJedz.pl
      </h1>
      <p
        className="mt-3 text-lg"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        Porównaj ceny dostaw jedzenia w Twojej okolicy
      </p>
    </main>
  );
}
