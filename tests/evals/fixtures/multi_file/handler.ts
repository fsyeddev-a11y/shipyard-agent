import { createUser } from "./service";
export function handleSignup(name: string) {
  const user = createUser(name);
  return user;
}
